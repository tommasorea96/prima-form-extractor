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
│   └── extractor.py       ← core NLP extraction engine (Claude API)
├── tools/
│   └── form-scraper/      ← separate Playwright tool to scrape Prima's form fields
├── CLAUDE.md
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

## Tech stack

- Python 3.10+
- Claude API (Anthropic) for NLP extraction
- FastAPI for the REST API layer (to be added)
- Playwright (for form-scraper tool only)

## Status

- [ ] Form scraper built and run → full field list extracted
- [ ] Field schema defined (JSON)
- [ ] Extraction engine built (Claude API)
- [ ] REST API wrapper (FastAPI)
- [ ] Tested end-to-end with sample Spanish inputs

## Next steps

1. Build `tools/form-scraper` using Playwright to get the full field list
2. Define the complete field schema as a JSON file
3. Build the extraction engine using Claude API
