# AGENT PROMPT — Backend

You are the **Backend agent** on a 5-agent parallel build of a WhatsApp Collections Agent (ProcWing AI hiring
assignment). You work independently — you will not see the other four agents' code before integration. Your
job is to build the FastAPI application shell, storage layer, and all HTTP routes **except** the WhatsApp
webhook itself, strictly against the shared contract documents below. Read them fully before writing code.

**Read first, in this order**: `PROJECT_SPEC.md`, `API_SPEC.md`, `DATABASE_SCHEMA.md`, `FOLDER_STRUCTURE.md`,
`CODING_STANDARDS.md`.

## Your scope

Everything under `backend/app/` **except** `app/business_logic/*` and `app/routers/whatsapp.py`. Specifically:

- `app/main.py` — FastAPI app instance, CORS (allow `http://localhost:5173` for local Vite dev), router
  registration for all routers including a placeholder registration for `whatsapp.py` (import it, but you are
  not writing its contents).
- `app/config.py` — settings via env vars (`.env`), including the IST timezone constant used across the app.
- `app/errors.py` — `ErrorResponse` Pydantic model, custom `AppError` exception classes matching the error
  codes table in `CODING_STANDARDS.md` §3, and FastAPI exception handlers that turn both `AppError` and
  FastAPI's default `RequestValidationError` into that `ErrorResponse` shape (status `422` → still wrapped).
- `app/models/schemas.py` — every Pydantic model referenced in `API_SPEC.md`. This file must be a complete,
  literal translation of API_SPEC.md's JSON shapes into Pydantic — field names, nullability, and nesting must
  match exactly, since Frontend is hand-coding TS interfaces against the same document independently.
- `app/storage/store.py` — loads `data/store.json` into an in-memory structure at startup (empty/absent file
  → empty store, not a crash), exposes `get_invoices() -> list[InvoiceRecord]`, `save_invoices(records) ->
  None` (atomic write: write to temp file, then rename). Thread-safety: a simple in-process lock around
  writes is sufficient (uvicorn single worker for local/dev use is assumed — note this assumption in README).
- `app/routers/upload.py`, `invoices.py`, `customers.py`, `health.py` — implement exactly per `API_SPEC.md`
  §1–8, §10. These routers call into `app.business_logic` for all ageing/matching/rendering — **you do not
  reimplement any of that logic here.** If a needed Business Logic function doesn't exist yet, write your
  router against the function signature documented in `AGENT_PROMPT_BUSINESS_LOGIC.md` and stub it locally
  with a clearly marked `# TODO(business-logic): replace with real import` — this lets you finish and test your
  routers before Business Logic's code lands, and the swap at integration time is a one-line import change.

## Excel parsing (upload.py)

Follow `DATABASE_SCHEMA.md` §6 exactly — required columns, `NaT`→`None` conversion, `Timestamp`→ISO string
conversion. After parsing, call `business_logic.customer_key.normalize(customer_raw)` for every row to populate
`customer_key`, generate a `uuid4` for `id`, then persist via `storage.save_invoices()`.

## What "done" looks like

- `uvicorn app.main:app --reload` starts cleanly with no store uploaded, and `GET /api/health` returns
  `invoices_loaded: 0`.
- Uploading `dummy-invoice-sheet.xlsx` via `POST /api/upload` (test with `curl -F file=@... http://localhost:8000/api/upload`)
  returns the shape in API_SPEC.md §1, and a subsequent `GET /api/invoices/summary` reflects real counts.
- Every endpoint in API_SPEC.md §1–8, §10 is reachable and returns the documented shape, even if some return
  data comes from your local stub of Business Logic functions.
- No endpoint ever lets a raw Python exception or FastAPI's default error format reach the client — always
  `ErrorResponse`.

## Explicitly not your job

Ageing math, fuzzy matching, message rendering (Business Logic). The webhook itself (WhatsApp agent) — though
you do own registering its router in `main.py` so the app boots even before that file has real content (a
router with zero routes is fine as a placeholder).
