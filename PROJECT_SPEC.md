# PROJECT_SPEC.md — WhatsApp Collections Agent

Source brief: `hiring-assignment-whatsapp-collections-agent.pdf` (ProcWing AI). This document translates that
brief into the architecture five independent agents will build against. If anything here conflicts with the
original PDF, the PDF wins — flag the conflict, don't silently resolve it.

## 1. What we're building

Two connected pieces sharing one data layer:

1. **Portal** — upload an AR sheet (`.xlsx`), parse and store invoice rows, browse them with bucket-filter
   tabs and search.
2. **WhatsApp Agent** — free-text query naming a customer ("Give me a weekly payment schedule for ABC") →
   fuzzy-matched to a customer → formatted WhatsApp message reply, generated live from the same stored data.

The portal's stored data **is** the WhatsApp agent's data source. There is no second copy of the data anywhere.

## 2. Stack (locked)

| Layer | Choice |
|---|---|
| Backend | Python, FastAPI |
| Frontend | React + TypeScript (Vite) |
| Storage | JSON file on disk (`backend/data/store.json`), loaded into memory at process start |
| WhatsApp | Twilio WhatsApp Sandbox, webhook into FastAPI |
| Validation | Pydantic v2 models (backend), hand-written matching TS interfaces (frontend) — see API_SPEC.md |

No database server, no ORM. This is intentional for a 500-row, 3-day assignment — do not introduce Postgres,
SQLite, or SQLAlchemy. See DATABASE_SCHEMA.md for exactly how the JSON store is structured and why ageing is
never persisted.

## 3. The five agent tracks

| Agent | Owns | Does NOT own |
|---|---|---|
| **Backend** | FastAPI app skeleton, routing, upload endpoint (xlsx parsing → store), storage read/write module, request/response wiring | Ageing math, fuzzy matching, message text — calls into Business Logic's functions |
| **Frontend** | React app: upload page, invoice list with bucket tabs + search | Any backend logic; consumes API_SPEC.md only |
| **Business Logic** | Ageing computation, weekly-window computation, customer summary aggregation, WhatsApp message rendering (both report types), fuzzy name resolution | HTTP layer, Twilio, React — pure Python functions, unit-testable in isolation |
| **WhatsApp** | Twilio webhook endpoint, incoming message parsing, routing free text to report type, calling Business Logic, sending the reply | Ageing math, message formatting internals — calls Business Logic's render functions |
| **QA** | Test suite (pytest) for ageing/due-this-week/edge cases, sample output generation for 3+ customers | Any implementation code |

Backend and Business Logic are deliberately separated: Business Logic is pure functions with no I/O, which is
what makes it independently testable by QA and independently buildable in parallel with Backend's HTTP plumbing.
**Backend imports Business Logic as a library; it never reimplements ageing or matching logic.**

## 4. Non-negotiable business rules

These come directly from the brief and are restated here because every agent needs to implement them
*identically* — see DATABASE_SCHEMA.md §3 for the precise formulas.

- **Ageing basis**: computed from `Due Date` against **today's date**, live at request time — never stored.
- **Overdue** = sum of Outstanding where `Due Date < today`.
- **Due This Week** = sum of Outstanding where `Due Date` falls in the current Mon–Fri window.
- **Ageing buckets**: `NOT_DUE`, `0-15`, `16-30`, `31-60`, `61-90`, `90+`, plus `NO_DUE_DATE` for the one
  invoice with a missing Due Date (excluded from Overdue/Due-This-Week, included in Total Outstanding).
- **Customer name matching is fuzzy**, not exact — the sheet has inconsistent casing and suffixes
  (`- Customer`, `Pvt Ltd` vs `Private Limited`). Exact-match-only is an explicit fail condition in the brief.
- **Two report types only** for now, but the interface must make adding a third a small change, not a rewrite
  (explicit evaluation criterion) — see AGENT_PROMPT_BUSINESS_LOGIC.md for the report-type contract.

## 5. Deliverables (per brief)

- Working code, runnable end to end (portal + agent)
- `README.md` — how to run, assumptions made, what's out of scope
- Sample output — both report types, for at least 3 customers, including one with no overdue invoices and one
  spanning every ageing bucket (QA agent owns generating this, using real names from `dummy-invoice-sheet.xlsx`
  once it's inspected)

## 6. Evaluation criteria (per brief — keep these in mind while building)

1. Correctness of ageing and due-this-week computation against today's date
2. Handling of edge cases: zero-outstanding customer, missing due dates, fuzzy name matches, name not found
3. Code structure — would adding a third query type be a small change or a rewrite
4. Output readability as an actual WhatsApp message a customer would receive

## 7. Timezone / "today" definition

All date logic uses **IST (Asia/Kolkata)**, calendar dates only (no time-of-day component). `today` is computed
once per request via a single shared function (`get_today()` in Business Logic) — never `date.today()` called
ad hoc in multiple places, since that risks two agents' code disagreeing at midnight boundaries.