"""
Prima Seguros form scraper — one-time internal tool.

Navigates https://calcular.helloprima.es/coche step by step using Playwright,
extracts all form fields (including conditionally shown ones), and writes the
full discovered schema to tools/form-scraper/fields.json.

Usage:
    python tools/form-scraper/scraper.py

Requirements:
    pip install playwright
    playwright install chromium
"""

import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright, Page, Locator

OUTPUT = Path(__file__).parent / "fields.json"
FORM_URL = "https://calcular.helloprima.es/coche"

# Dummy values used to advance through the form steps and trigger conditional fields.
# Adjust if the form rejects these values.
FILL_VALUES = {
    "purchase_timeline": "ya_tengo",     # "already owned" → unlocks previous-insurance section
    "license_plate": "1234ABC",          # arbitrary plate
    "had_previous_insurance": True,      # trigger insurer / no-claims fields
    "previous_insurer": "Mapfre",
    "years_without_claims": "3",
    "coverage_type": "terceros_basico",
    "first_name": "Mario",
    "last_name": "Rossi",
    "birth_date": "05/03/1990",
    "id_number": "12345678Z",
    "residence_postal_code": "28001",
    "years_with_license": "10",
    "penalty_points": "0",
    "claims_history": "0",
    "phone": "600000000",
    "email": "test@test.com",
}


def extract_fields_from_page(page: Page, step: int) -> list[dict]:
    """Pull every visible form field from the current page state."""
    fields = []

    # --- text / number / date / email / tel inputs ---
    for el in page.locator("input:visible").all():
        field = _input_field(el, step)
        if field:
            fields.append(field)

    # --- select dropdowns ---
    for el in page.locator("select:visible").all():
        field = _select_field(el, step)
        if field:
            fields.append(field)

    # --- radio groups ---
    radio_names = set()
    for el in page.locator("input[type=radio]:visible").all():
        name = el.get_attribute("name") or ""
        if name and name not in radio_names:
            radio_names.add(name)
            field = _radio_group(page, name, step)
            if field:
                fields.append(field)

    # --- checkboxes ---
    for el in page.locator("input[type=checkbox]:visible").all():
        field = _checkbox_field(el, step)
        if field:
            fields.append(field)

    # deduplicate by field_id
    seen = set()
    unique = []
    for f in fields:
        if f["field_id"] not in seen:
            seen.add(f["field_id"])
            unique.append(f)
    return unique


def _label_for(el: Locator, page: Page) -> str:
    """Try several strategies to find the human-readable label for an element."""
    try:
        el_id = el.get_attribute("id")
        if el_id:
            label = page.locator(f"label[for='{el_id}']").first
            if label.count() > 0:
                return label.inner_text().strip()
        # aria-label
        aria = el.get_attribute("aria-label") or ""
        if aria:
            return aria.strip()
        # placeholder as fallback
        ph = el.get_attribute("placeholder") or ""
        return ph.strip()
    except Exception:
        return ""


def _field_id(el: Locator, fallback: str = "") -> str:
    """Derive a stable snake_case field id."""
    raw = (
        el.get_attribute("name")
        or el.get_attribute("id")
        or el.get_attribute("data-field")
        or fallback
    )
    return re.sub(r"[^a-z0-9]+", "_", (raw or "unknown").lower()).strip("_")


def _input_field(el: Locator, step: int) -> dict | None:
    itype = el.get_attribute("type") or "text"
    if itype in ("radio", "checkbox", "submit", "button", "hidden"):
        return None
    fid = _field_id(el)
    if fid in ("", "unknown"):
        return None
    return {
        "step": step,
        "field_id": fid,
        "type": itype,
        "label": _label_for(el, el.page),
        "placeholder": el.get_attribute("placeholder") or "",
        "required": el.get_attribute("required") is not None,
        "options": None,
        "conditional_on": None,
    }


def _select_field(el: Locator, step: int) -> dict | None:
    fid = _field_id(el)
    if fid in ("", "unknown"):
        return None
    options = [
        o.get_attribute("value") or o.inner_text().strip()
        for o in el.locator("option").all()
        if (o.get_attribute("value") or "").strip()
    ]
    return {
        "step": step,
        "field_id": fid,
        "type": "select",
        "label": _label_for(el, el.page),
        "placeholder": None,
        "required": el.get_attribute("required") is not None,
        "options": options,
        "conditional_on": None,
    }


def _radio_group(page: Page, name: str, step: int) -> dict | None:
    radios = page.locator(f"input[type=radio][name='{name}']:visible").all()
    if not radios:
        return None
    options = [r.get_attribute("value") for r in radios if r.get_attribute("value")]
    fid = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    # find label from first radio's label element
    label = ""
    try:
        first_id = radios[0].get_attribute("id")
        if first_id:
            lbl = page.locator(f"label[for='{first_id}']").first
            if lbl.count() > 0:
                label = lbl.inner_text().strip()
    except Exception:
        pass
    return {
        "step": step,
        "field_id": fid,
        "type": "radio",
        "label": label,
        "placeholder": None,
        "required": True,
        "options": options,
        "conditional_on": None,
    }


def _checkbox_field(el: Locator, step: int) -> dict | None:
    fid = _field_id(el)
    if fid in ("", "unknown"):
        return None
    return {
        "step": step,
        "field_id": fid,
        "type": "boolean",
        "label": _label_for(el, el.page),
        "placeholder": None,
        "required": el.get_attribute("required") is not None,
        "options": None,
        "conditional_on": None,
    }


def try_advance(page: Page) -> bool:
    """Click the primary CTA / next button. Return True if page changed."""
    url_before = page.url
    for selector in [
        "button[type=submit]",
        "button:has-text('Siguiente')",
        "button:has-text('Continuar')",
        "button:has-text('Calcular')",
        "a:has-text('Siguiente')",
        "input[type=submit]",
    ]:
        try:
            btn = page.locator(selector).first
            if btn.count() > 0 and btn.is_visible():
                btn.click()
                page.wait_for_load_state("networkidle", timeout=8000)
                if page.url != url_before or _new_fields_visible(page):
                    return True
        except Exception:
            continue
    return False


def _new_fields_visible(page: Page) -> bool:
    return page.locator("input:visible, select:visible").count() > 0


def run_scraper() -> list[dict]:
    all_fields: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)  # headless=False helps with bot detection
        context = browser.new_context(
            locale="es-ES",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        print(f"Opening {FORM_URL} ...")
        page.goto(FORM_URL, wait_until="networkidle")
        page.wait_for_timeout(2000)

        step = 1
        max_steps = 10  # safety cap

        while step <= max_steps:
            print(f"\n--- Step {step} ---")

            # Capture fields visible at the start of this step
            fields_before = extract_fields_from_page(page, step)
            print(f"  Fields found: {[f['field_id'] for f in fields_before]}")
            all_fields.extend(fields_before)

            # Try to fill known fields to unlock conditional ones
            _fill_known_fields(page)
            page.wait_for_timeout(1000)

            # Capture any newly revealed conditional fields
            fields_after = extract_fields_from_page(page, step)
            known_ids = {f["field_id"] for f in fields_before}
            conditional_fields = [f for f in fields_after if f["field_id"] not in known_ids]
            if conditional_fields:
                print(f"  Conditional fields unlocked: {[f['field_id'] for f in conditional_fields]}")
                for f in conditional_fields:
                    f["conditional_on"] = "previous_field_value"  # refined manually later
                all_fields.extend(conditional_fields)

            # Try to move to the next step
            advanced = try_advance(page)
            if not advanced:
                print("  Could not advance — assuming last step.")
                break
            page.wait_for_timeout(1500)
            step += 1

        browser.close()

    return all_fields


def _fill_known_fields(page: Page) -> None:
    """Best-effort: fill fields we know about to trigger conditional logic."""
    fv = FILL_VALUES

    # radio buttons
    for name, value in fv.items():
        try:
            radio = page.locator(f"input[type=radio][name='{name}'][value='{value}']:visible").first
            if radio.count() > 0:
                radio.click()
        except Exception:
            pass

    # text / date / number inputs
    for name, value in fv.items():
        if isinstance(value, bool):
            continue
        for attr in ("name", "id"):
            try:
                el = page.locator(f"input[{attr}='{name}']:visible").first
                if el.count() > 0 and el.get_attribute("type") not in ("radio", "checkbox"):
                    el.fill(str(value))
                    break
            except Exception:
                pass

    # checkboxes (boolean fields)
    for name, value in fv.items():
        if not isinstance(value, bool):
            continue
        for attr in ("name", "id"):
            try:
                el = page.locator(f"input[type=checkbox][{attr}='{name}']:visible").first
                if el.count() > 0:
                    if value and not el.is_checked():
                        el.click()
                    elif not value and el.is_checked():
                        el.click()
                    break
            except Exception:
                pass

    # selects
    for name, value in fv.items():
        if isinstance(value, bool):
            continue
        for attr in ("name", "id"):
            try:
                el = page.locator(f"select[{attr}='{name}']:visible").first
                if el.count() > 0:
                    el.select_option(str(value))
                    break
            except Exception:
                pass


if __name__ == "__main__":
    fields = run_scraper()
    OUTPUT.write_text(json.dumps(fields, ensure_ascii=False, indent=2))
    print(f"\nDone. {len(fields)} fields written to {OUTPUT}")
