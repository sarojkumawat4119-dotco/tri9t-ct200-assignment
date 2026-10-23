# Tri9T AI — CT-200 Traceable QA API

A CT-200-specific document ingestion and traceability backend. It extracts the PDF text layer with PyMuPDF, falls back to Tesseract OCR for pages with no usable text layer, reconstructs numbered section hierarchy, versions ingested PDFs, pins selections to exact source snapshots, generates structured QA test ideas, and reports whether generation sources changed.

> **Safety boundary:** generated cases are engineering ideas, not validated medical-device verification protocols. Review by qualified engineering/quality personnel is required before execution.

## What is included

- FastAPI + Pydantic + SQLAlchemy + SQLite for document versions, nodes, and version-pinned selections.
- JSON document store (`data/generated_cases.json`) for immutable generated output and source provenance. JSON is justified for this small single-process assignment; it is not a concurrent multi-writer production store.
- Content hashes based on whitespace-normalized text; logical IDs matched using numbered heading + ancestor path, intentionally excluding body hash.
- Bounded two-attempt LLM response validation; if no API key is configured, a clearly labelled deterministic local fallback supports end-to-end demonstrations.
- Retrieval by generation, selection ID, or node ID, with queryable staleness status.

## Setup

Python 3.10+ recommended.

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Windows: copy .env.example .env
```

Optional real LLM generation: set `LLM_PROVIDER=groq` and `LLM_API_KEY` in `.env` (Groq API key), or set `LLM_PROVIDER=gemini` with a Gemini API key. Add the relevant SDK (`pip install groq`) for Groq; Gemini uses `requests`. With no key, the API uses local fallback cases, explicitly labelled as `local-fallback`.

## Run

```bash
uvicorn app.main:app --reload
```

Swagger UI: http://127.0.0.1:8000/docs

## Ingest v1 → v2

Run these from the repository root in separate requests. Relative paths resolve from the process working directory.

```bash
curl -X POST http://127.0.0.1:8000/ingest -H "Content-Type: application/json" -d '{"pdf_path":"data/ct200_manual.pdf"}'
curl -X POST http://127.0.0.1:8000/ingest -H "Content-Type: application/json" -d '{"pdf_path":"data/ct200_manual_v2.pdf"}'
curl http://127.0.0.1:8000/versions
curl "http://127.0.0.1:8000/sections?version=1"
curl "http://127.0.0.1:8000/nodes/search?q=Battery&version=1"
```

The ingestion endpoint is content-idempotent: submitting identical PDF bytes does not create a duplicate version. A new PDF becomes the next version of the same CT-200 manual.

## Selection, generation, and stale retrieval

Use IDs returned from `/nodes/search` (IDs are database-generated and will differ by local database).

```bash
curl -X POST http://127.0.0.1:8000/selections -H "Content-Type: application/json" -d '{"name":"Battery and inflation requirements v1","node_ids":[7,11]}'
curl -X POST http://127.0.0.1:8000/generate -H "Content-Type: application/json" -d '{"selection_id":1}'
curl "http://127.0.0.1:8000/generations?selection_id=1"
curl "http://127.0.0.1:8000/generations?node_id=7"
curl http://127.0.0.1:8000/generations/<generation_id>
curl http://127.0.0.1:8000/nodes/<node_id>/changes
```

Selections are version-pinned and store source snapshots, so generation reconstructs the exact selected text even after v2 is ingested. `/generations` and `/generations/{id}` expose staleness status at retrieval time. The examples use illustrative IDs; use IDs returned by your running API.

## API summary

| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | Liveness |
| POST | `/ingest` | Ingest a PDF as a new version |
| GET | `/versions` | List ingested versions |
| GET | `/sections?version=N` | List top-level sections; defaults to latest |
| GET | `/nodes/{id}` | Node, body, hash and descendants |
| GET | `/nodes/search?q=...&version=N` | Search headings/body |
| GET | `/nodes/{id}/changes` | Compare a node with its latest logical match |
| POST | `/selections` | Create a version-pinned named selection |
| GET | `/selections/{id}` | Retrieve pinned text snapshots |
| POST | `/generate` | Generate 3–5 validated test-case ideas |
| GET | `/generations?selection_id=N` | Retrieve generations and staleness by selection |
| GET | `/generations?node_id=N` | Retrieve generations sourced from a node |
| GET | `/generations/{generation_id}` | Retrieve exact output, provenance and staleness |

## Tests

```bash
pytest -q
```

Tests explicitly cover duplicate “Error Codes” headings under different parents, the missing `2.1.1` intermediate heading, out-of-order `3.4`/`3.3`, a paragraph split across a page boundary, v1/v2 requirement changes, and preservation of table rows.

## Known limitations

- This is a parser tuned to the supplied CT-200 manuals, not a generic PDF parser. The current manuals have extractable text layers; OCR fallback is only activated for pages with very little extracted text. OCR output should be visually verified.
- Heading hierarchy relies on numbering and short-line heuristics. Unnumbered headings, multi-column layouts, ambiguous numbered lists, scanned tables, or numbering changes can defeat it. Unsupported cases should be surfaced during validation rather than assumed correct.
- Table content is preserved as line-oriented text, not a fully typed cell grid. The original manual's table alignment is simplified by text extraction.
- Matching uses heading number + normalized ancestor path. Renumbering or heading changes can cause false removals/new identities; repeated identical section paths are disambiguated by occurrence order. Body hashes detect textual change, not semantic impact.
- The JSON generation store uses atomic file replacement but is not safe for concurrent multi-process writers. Use MongoDB or a transactional store for production.
- Staleness means “source text changed or no logical match,” not that the generated test case is definitely invalid. Clinical impact classification and human review are not automated.
