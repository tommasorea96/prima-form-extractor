"""
Prima Form Extractor — Extraction Engine

Takes a conversation (list of {role, text} messages in Spanish) and returns
structured field data mapped to Prima Seguros' quote form.

Uses Claude API with prompt caching on the system prompt + schema (stable across requests).
"""

import json
import os
import re
from pathlib import Path
from functools import lru_cache

import anthropic
from dotenv import load_dotenv

load_dotenv()

_SCHEMA_PATH = Path(__file__).parent / "schema.json"
_MODEL = "claude-opus-4-6"
_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


@lru_cache(maxsize=1)
def _load_schema() -> list[dict]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _build_system_prompt() -> str:
    schema = _load_schema()

    # Serialise schema deterministically so the cache key is stable
    schema_json = json.dumps(schema, ensure_ascii=False, sort_keys=True, indent=2)

    return f"""Eres un extractor de datos para Prima Seguros (seguro de coche español).
Tu tarea es analizar una conversación en español y extraer los datos del formulario de cotización.

## Esquema de campos

A continuación se define cada campo que debes intentar extraer:

{schema_json}

## Instrucciones

1. Lee toda la conversación y extrae el valor de cada campo definido en el esquema.
2. Si un campo no aparece en la conversación, devuelve null para ese campo.
3. Para los campos condicionales (conditional_on != null), si la condición no se cumple
   devuelve la cadena "N/A" en lugar de null.
4. Normaliza los valores según el tipo indicado:
   - date → formato YYYY-MM-DD (ej. "5 de marzo de 1990" → "1990-03-05")
   - integer → número entero sin texto (ej. "diez años" → 10)
   - boolean → true o false
   - enum → uno de los valores permitidos en options (ej. "todo riesgo" → "todo_riesgo_con_franquicia")
   - string → texto limpio sin espacios extra
5. Para birth_date, si el usuario menciona su edad pero no su fecha de nacimiento exacta,
   estima el año aproximado restando la edad al año actual (2026).
6. Devuelve ÚNICAMENTE un objeto JSON válido con todos los field_id como claves.
   No incluyas explicaciones, markdown ni ningún texto adicional fuera del JSON.

## Formato de respuesta requerido

{{
  "purchase_timeline": null | "ya_tengo" | "nuevo" | "usado_concesionario" | "usado_particular",
  "license_plate": null | string,
  "registration_date": null | "YYYY-MM-DD",
  "brand": null | string,
  "model": null | string,
  "first_name": null | string,
  "last_name": null | string,
  "birth_date": null | "YYYY-MM-DD",
  "id_number": null | string,
  "residence_postal_code": null | string,
  "years_with_license": null | integer,
  "penalty_points": null | integer,
  "claims_history": null | integer,
  "had_previous_insurance": null | true | false,
  "previous_insurer": null | "N/A" | string,
  "years_without_claims": null | "N/A" | integer,
  "coverage_type": null | "terceros_basico" | "terceros_ampliado" | "todo_riesgo_con_franquicia",
  "phone": null | string,
  "email": null | string
}}"""


def _build_transcript(messages: list[dict]) -> str:
    """Flatten the messages array into a readable Spanish transcript."""
    lines = []
    for msg in messages:
        role = msg.get("role", "user")
        text = msg.get("text", "").strip()
        if not text:
            continue
        label = "Cliente" if role == "user" else "Agente"
        lines.append(f"{label}: {text}")
    return "\n".join(lines)


def _apply_conditional_logic(extracted: dict) -> dict:
    """
    Post-process conditional fields:
    - If had_previous_insurance is False, mark dependent fields as "N/A"
    - If purchase_timeline is not "ya_tengo", had_previous_insurance section is N/A
    """
    result = dict(extracted)

    # Conditional: previous insurance section only applies if purchase_timeline == "ya_tengo"
    if result.get("purchase_timeline") and result["purchase_timeline"] != "ya_tengo":
        result["had_previous_insurance"] = "N/A"
        result["previous_insurer"] = "N/A"
        result["years_without_claims"] = "N/A"

    # Conditional: insurer and years_without_claims only if had_previous_insurance == True
    elif result.get("had_previous_insurance") is False:
        result["previous_insurer"] = "N/A"
        result["years_without_claims"] = "N/A"

    return result


def _compute_missing(extracted: dict) -> list[str]:
    """Return required fields whose value is null (not N/A, not a real value)."""
    schema = _load_schema()
    required_ids = {f["field_id"] for f in schema if f.get("required")}
    return [
        fid for fid in required_ids
        if extracted.get(fid) is None
    ]


def extract(messages: list[dict]) -> dict:
    """
    Extract structured form data from an unstructured Spanish conversation.

    Args:
        messages: list of {"role": "user"|"assistant", "text": "..."}

    Returns:
        {
            "extracted": {field_id: value, ...},   # all fields, null if not found
            "missing": [field_id, ...]              # required fields with null values
        }
    """
    client = _get_client()
    system_prompt = _build_system_prompt()
    transcript = _build_transcript(messages)

    user_content = (
        "Extrae los datos del formulario de la siguiente conversación:\n\n"
        f"{transcript}\n\n"
        "Responde únicamente con el objeto JSON."
    )

    response = client.messages.create(
        model=_MODEL,
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                # Cache the system prompt + schema — it only changes when the schema does
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {"role": "user", "content": user_content}
        ],
    )

    raw = next(
        (block.text for block in response.content if block.type == "text"),
        "{}"
    )

    # Strip any markdown fences Claude might wrap the JSON in
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw)

    try:
        extracted = json.loads(raw)
    except json.JSONDecodeError:
        # Graceful fallback: return all nulls so the API doesn't crash
        schema = _load_schema()
        extracted = {f["field_id"]: None for f in schema}

    extracted = _apply_conditional_logic(extracted)
    missing = _compute_missing(extracted)

    return {
        "extracted": extracted,
        "missing": missing,
    }
