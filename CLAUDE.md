# Prima Form Extractor — Project Context

## What this project is

A B2B SaaS tool to be sold to Prima Seguros (Spanish car insurance company).
It extracts structured form data from unstructured text inputs (WhatsApp messages, chatbot conversations, voice transcripts) and maps them to the fields required by Prima's car insurance quote form.

Prima integrates this tool via API into their existing systems.

## Business context

- **Customer:** Prima Seguros (helloprima.es)
- **Language:** Spanish only (for now)
- **Sold as:** an API that Prima integrates on their side
- **Goal:** reduce friction in form filling by allowing unstructured input like "Soy Mario Rossi, tengo 35 años" to be automatically mapped to structured fields

## Architecture

```
prima-form-extractor/
├── src/
│   ├── __init__.py
│   ├── schema.json        ← canonical field schema (19 fields, types, conditionals, Spanish hints)
│   ├── extractor.py       ← core NLP extraction engine (Claude API, with prompt caching)
│   ├── api.py             ← FastAPI REST API (POST /extract)
│   └── main.py            ← uvicorn entrypoint
├── tools/
│   └── form-scraper/
│       └── scraper.py     ← one-time Playwright scraper to discover Prima's form fields
├── CLAUDE.md
├── .env.example           ← ANTHROPIC_API_KEY template (.env is gitignored)
├── .gitignore
└── requirements.txt
```

## Components

### 1. Extraction Engine (main product) — `src/extractor.py`
- Takes unstructured Spanish text as input
- Uses Claude API to extract named entities and map them to form fields
- Returns structured JSON output
- Handles conditional fields (e.g. previous insurer only appears if user had prior insurance)
- Input sources: WhatsApp text, chatbot conversation, voice transcript

### 2. Form Scraper (internal tool) — `tools/form-scraper/`
- Uses Playwright to navigate Prima's quote form at https://calcular.helloprima.es/coche
- Extracts all fields, steps, and conditional logic
- Output used to build the field schema for the extraction engine
- NOT part of the product sold to Prima

## Prima's Form — Known fields

The form has 6 steps. Fields confirmed so far:

**Step 1 — Tu Coche (Your Car)**
- purchase_timeline: enum (already owned / new / used from dealer / used from private)
- license_plate: string (auto-populates vehicle data)

**Vehicle data (auto-filled from plate)**
- registration_date: date
- brand: string
- model: string

**Driver data**
- first_name: string
- last_name: string
- birth_date: date
- id_number: string (DNI/NIE)
- residence_postal_code: string
- years_with_license: integer
- penalty_points: integer
- claims_history: integer (number of claims)

**Previous insurance (conditional — only if already owned)**
- had_previous_insurance: boolean
- previous_insurer: string (only if had_previous_insurance = true)
- years_without_claims: integer (only if had_previous_insurance = true)

**Coverage**
- coverage_type: enum (terceros básico / terceros ampliado / todo riesgo con franquicia)

**Contact**
- phone: string
- email: string

> NOTE: Full field list to be completed once form-scraper tool is built and run against https://calcular.helloprima.es/coche

## Conditional logic

Some fields only exist if other fields have certain values:
- `previous_insurer` and `years_without_claims` → only if `had_previous_insurance = true`
- More conditional rules to be discovered via form-scraper

## API contract

**Request:** `POST /extract`
```json
{
  "messages": [
    {"role": "user", "text": "Me llamo Mario Rossi, tengo 35 años..."},
    {"role": "assistant", "text": "¿Cuál es tu código postal?"},
    {"role": "user", "text": "28001"}
  ]
}
```

**Response:**
```json
{
  "extracted": {
    "first_name": "Mario",
    "last_name": "Rossi",
    "birth_date": "1991-01-01",
    "residence_postal_code": "28001",
    "coverage_type": null
  },
  "missing": ["coverage_type", "license_plate", "phone", "email", ...]
}
```

- `extracted`: all fields, `null` if not found, `"N/A"` if conditional and not applicable
- `missing`: required fields that are still `null`
- No auth for now

## Tech stack

- Python 3.10+
- Claude API (`claude-opus-4-6`) for NLP extraction, with prompt caching on the schema
- FastAPI for the REST API layer
- Playwright (for form-scraper tool only)
- Run: `uvicorn src.main:app --reload` (from project root)

## Status

- [x] Form scraper built (`tools/form-scraper/scraper.py`) — not yet run against Prima's site
- [x] Field schema defined (`src/schema.json`) — 19 fields, based on known data; to be updated after scraper runs
- [x] Extraction engine built and tested (`src/extractor.py`)
- [x] REST API wrapper built (`src/api.py`)
- [ ] Form scraper actually run → full field list verified
- [ ] Tested end-to-end with real Prima form data

## Next steps

1. Run `python tools/form-scraper/scraper.py` against https://calcular.helloprima.es/coche
2. Review output and update `src/schema.json` with any missing/corrected fields
3. Start API with `uvicorn src.main:app --reload` and test with real Spanish inputs
