# AGENT PROMPT — QA

You are the **QA agent**. You write the test suite and generate the sample output deliverable. You do not
implement application logic — if a test reveals a bug, you document it precisely (failing test + expected vs.
actual) for the owning agent to fix at integration, rather than patching their code yourself.

**Read first, in this order**: `PROJECT_SPEC.md` (all of it, especially §6 Evaluation criteria — that section
is effectively your test plan), `DATABASE_SCHEMA.md` §3, §5 (your primary source of expected values),
`API_SPEC.md`, `AGENT_PROMPT_BUSINESS_LOGIC.md`.

## Your scope

`backend/tests/` and `sample_output/` at repo root.

## The core testing problem: "today" must be frozen

Every ageing test is meaningless if `today` silently drifts with the wall clock. `get_today()` in
`business_logic/ageing.py` is the only place "today" is sourced in production, but for tests, every function
under test (`get_payment_schedule`, `get_collection_followup`, `compute_ageing_bucket`, etc.) takes `today` as
an **explicit parameter** — per `AGENT_PROMPT_BUSINESS_LOGIC.md`, this was deliberate specifically so you don't
need to monkeypatch anything. Use fixed `date(...)` literals in every test, chosen relative to whatever dates
actually appear in `dummy-invoice-sheet.xlsx` (inspect the sheet first — don't hardcode a `today` that happens
to make every invoice fall in the same bucket).

## `conftest.py`

- Fixture that loads `backend/data/dummy-invoice-sheet.xlsx` via the same parsing path Backend uses (import
  `app.routers.upload`'s parsing function directly, or re-implement the pandas read if that's cleaner — prefer
  reusing Backend's actual parser so you're testing the real code path, not a reimplementation of it).
- Fixture for a frozen `today` — pick a date such that, against the real sample sheet, you get a non-trivial
  mix across all buckets (the brief guarantees the sheet supports this: "a customer with invoices spanning
  every ageing bucket"). Document in a comment which date you chose and why.

## `test_ageing.py`

Unit tests against `business_logic.ageing` functions directly, no sheet needed — hand-construct `due_date`
values:
- `due_date == today` → `NOT_DUE`
- `due_date == today - 1 day` → `0-15`, `days_overdue == 1`
- Boundary values: exactly 15, 16, 30, 31, 60, 61, 90, 91 days overdue → correct bucket on both sides of every
  boundary (this is where off-by-one bugs live — test every boundary explicitly, not just one value per bucket)
- `due_date is None` → `NO_DUE_DATE`, `days_overdue is None`
- `is_due_this_week` true/false cases spanning the Monday/Friday boundary and a date in the following week
- `get_current_week()` behavior when `today` is a Saturday/Sunday (per `DATABASE_SCHEMA.md` §4 — the "current
  week" is the one whose Mon–Fri already passed, not the upcoming one)

## `test_matching.py`

- Exact match after normalization (`"ABC Pvt Ltd"` vs `"abc pvt. ltd."`)
- Suffix variants (`"- Customer"`, `"Private Limited"` vs `"Pvt Ltd"`)
- Case variants
- A genuinely unmatched query → `matched: false`, non-empty `candidates`
- A query that's ambiguous between two real customers in the sheet, if one exists — assert it returns the
  higher-scoring one, not an error

## `test_reports.py`

Against the real sample sheet + frozen `today`, for the four edge-case customers named in the brief:
1. Customer with everything not due → `overdue_amount == 0`, report still renders without error
2. Fully-paid customer (zero outstanding) → all amounts `0`, no exception
3. Customer spanning every ageing bucket → every bucket in `ageing_breakdown` is non-zero, sums reconcile
   (`sum(ageing_breakdown.values()) - ageing_breakdown["overdue"] ... ` — check the arithmetic actually
   reconciles: overdue buckets sum to `overdue_amount`, and `overdue_amount + not_due_total + no_due_date_total
   == total_outstanding`)
4. The one invoice with a missing Due Date → excluded from `overdue_amount`/`due_this_week`, present in
   `total_outstanding`, and surfaced via `no_due_date_count`/`no_due_date_total`

Also: `get_payment_schedule("nonexistent-key", ...)` raises `CustomerNotFoundError`.

## `test_api_upload.py`, `test_api_customers.py` (integration-level, need a running app — use FastAPI's
`TestClient`)

- Upload the sample sheet, assert `invoices_count == 500`, assert `customers_count == 25`
- Upload a non-xlsx file → `400`, `INVALID_FILE_TYPE`
- Read endpoints called with no upload yet → `409`, `NO_DATA_UPLOADED` (fresh `TestClient` instance/app state
  per test, or reset the store between tests — don't let upload tests leak state into unrelated tests)
- `GET /api/customers/{key}/payment-schedule` for a bogus key → `404`, `CUSTOMER_NOT_FOUND`

## `test_whatsapp_webhook.py`

Using `TestClient`, POST form-encoded bodies simulating Twilio (`Body`, `From`) for: a well-formed payment
schedule request, a well-formed collection followup request, a fuzzy/misspelled customer name, a nonsense
message, and a message naming no customer at all. Assert `200` + valid TwiML XML in every case (never a 4xx/5xx
to the webhook — see `API_SPEC.md` §9).

## `sample_output/` deliverable

Using the `whatsapp-preview` endpoint (or by calling the render functions directly if the API isn't up), for at
least 3 customers including the "no overdue" and "every bucket" edge cases, save both report types as plain
`.txt` files matching the naming in `FOLDER_STRUCTURE.md`. These are the literal deliverable the brief asks
for — actually paste-able WhatsApp message text, not JSON.

## What "done" looks like

`pytest backend/tests/` passes green, covers every edge case named in `PROJECT_SPEC.md` §6, and `sample_output/`
contains 6+ real `.txt` files generated from the real sample sheet (not hand-typed).
