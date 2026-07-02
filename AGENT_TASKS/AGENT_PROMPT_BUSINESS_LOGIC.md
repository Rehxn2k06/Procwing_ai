# AGENT PROMPT — Business Logic

You are the **Business Logic agent**. You own every piece of actual reasoning in this system: ageing, the
current-week window, customer name normalization, fuzzy matching, and rendering both WhatsApp report types.
Backend and WhatsApp both import your functions as a library — they contain no ageing or matching logic of
their own. This is the most evaluation-sensitive track (the brief's #1 and #2 evaluation criteria — ageing
correctness and edge case handling — live entirely in your code) and the one QA tests most directly.

**Read first, in this order**: `PROJECT_SPEC.md` §4, §7, `DATABASE_SCHEMA.md` (all of it — this is your spec),
`API_SPEC.md` §6–8 (the shapes you must produce), `CODING_STANDARDS.md` §1 and §4.

## Hard constraint

`backend/app/business_logic/` has **zero imports** of FastAPI, Pydantic, or anything from `app/routers` or
`app/storage`. Pure Python + `rapidfuzz` + stdlib (`datetime`, `dataclasses`, `zoneinfo`). Functions take plain
Python objects (dataclasses or dicts, your call — but be consistent) in and return plain Python objects out.
This is what lets QA unit-test you in isolation and what lets you finish before Backend's HTTP layer exists.

## Files and required functions

### `ageing.py`
- `IST = ZoneInfo("Asia/Kolkata")`
- `get_today() -> date` — single source of truth for "today" everywhere in the app. Accepts no override in
  production, but see AGENT_PROMPT_QA.md for how tests freeze it.
- `get_current_week(today: date) -> tuple[date, date]` — returns `(monday, friday)` per DATABASE_SCHEMA.md §4.
- `compute_ageing_bucket(due_date: date | None, today: date) -> str` — exact formula in DATABASE_SCHEMA.md §3.
- `compute_days_overdue(due_date: date | None, today: date) -> int | None`
- `compute_is_due_this_week(due_date: date | None, week_start: date, week_end: date) -> bool`

### `customer_key.py`
- `normalize(customer_raw: str) -> str` — exact algorithm in DATABASE_SCHEMA.md §2. Write this as pure string
  manipulation, no external NLP library — it's a fixed suffix-stripping rule, not fuzzy.

### `matching.py`
- `resolve_customer_name(query: str, customers: list[CustomerRef]) -> MatchResult` where `CustomerRef` is a
  small dataclass `(customer_key, display_name)` and `MatchResult` mirrors `API_SPEC.md` §5's response shape.
- Use `rapidfuzz.fuzz.token_sort_ratio` (handles word-order and suffix noise well) against `display_name`
  **and** against `customer_key` (normalize the query the same way first, then also fuzzy-match the normalized
  forms — catches cases where casing/suffix differences alone would already resolve exactly via `customer_key`
  before fuzzy scoring even kicks in; check exact `customer_key` match first as a fast path, fall back to fuzzy
  scoring only if no exact key match).
- Match threshold: score `>= 70` on a 0–100 scale to accept a top match as `matched: true`. Below that,
  `matched: false` but still return the top 3 candidates (whatever their score) so the caller can show a
  helpful "did you mean" rather than a bare not-found.
- Document this threshold choice as a named constant (`MATCH_THRESHOLD = 70`) — QA will write tests around it
  and may push back on the number; that's expected, not a bug.

### `reports.py`
- `get_payment_schedule(customer_key: str, invoices: list[InvoiceRecord], today: date) -> PaymentSchedule`
  — full computation per `API_SPEC.md` §6. Raise a `CustomerNotFoundError` (plain Python exception, defined in
  this module) if `customer_key` has zero matching invoices — Backend catches this and maps it to the 404
  `CUSTOMER_NOT_FOUND` error.
- `get_collection_followup(customer_key: str, invoices: list[InvoiceRecord], today: date) -> CollectionFollowup`
  — per `API_SPEC.md` §7, including the 7-entry `daily_breakdown` per `DATABASE_SCHEMA.md` §3.
- Both functions take `today` as an explicit parameter (don't call `get_today()` internally) — this is what
  makes them trivially testable against fixed dates without monkeypatching the clock.

### `render.py`
- `format_inr(amount: float) -> str` — Indian digit grouping with `₹` prefix. One implementation, used
  everywhere currency appears in a WhatsApp message.
- `format_date_ddmonyyyy(d: date) -> str` — e.g. `04-Jul-2026`.
- `render_payment_schedule_message(schedule: PaymentSchedule) -> str` — adapt the Task 1 reference mockup
  (email HTML) into WhatsApp plain text/markdown per `CODING_STANDARDS.md` §4: `*bold*` headers, ageing
  breakdown as aligned plain-text lines (not a literal table), invoice list appended (your choice, per the
  brief, whether inline or as a second message — document which you chose and why in a docstring).
- `render_collection_followup_message(followup: CollectionFollowup) -> str` — same idea for Task 2, including
  the day-by-day breakdown as readable plain text (label: amount per line, not an ASCII table — WhatsApp
  clients render monospace tables inconsistently).

## Adding a third report type (evaluation criterion — design for this now)

Structure `reports.py` and `render.py` so a third report type is: one new `get_x_report()` function, one new
`render_x_message()` function, and one new entry in whatever dispatch mapping the WhatsApp agent uses to route
free text to a function (see `AGENT_PROMPT_WHATSAPP.md` — that mapping lives in `whatsapp.py`, not here, but
your two functions are the only things it needs to add). If adding a third type would require touching
`ageing.py` or `matching.py`, that's a sign those modules aren't sufficiently generic — keep them report-type-
agnostic.

## What "done" looks like

Every function above exists, is fully typed, has a one-line docstring, and can be exercised from a plain Python
REPL or pytest with no FastAPI app running — `from app.business_logic.reports import get_payment_schedule` and
call it directly against a hand-built list of invoice dicts/dataclasses and a fixed `today`.
