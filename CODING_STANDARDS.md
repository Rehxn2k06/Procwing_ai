# CODING_STANDARDS.md

Applies to all five agents. The goal is that code from any two tracks can sit in the same file review and look
like one person wrote it.

## 1. Python (backend/)

- **Formatting**: `black` defaults (line length 88... actually use `black`'s default 88, don't argue with it).
  `isort` for import ordering, profile `black`.
- **Typing**: every function signature is fully typed, including return type. `from __future__ import
  annotations` at the top of every module. No untyped `dict`/`list` in public function signatures — use the
  Pydantic models from `app/models/schemas.py`, or explicit `TypedDict`/dataclasses in `business_logic/` where
  Pydantic would be overkill (business_logic has no FastAPI dependency, so prefer `@dataclass` there over
  Pydantic — keeps that layer framework-free).
- **Naming**: `snake_case` for functions/variables/modules, `PascalCase` for classes and Pydantic models,
  `UPPER_SNAKE_CASE` for constants (e.g. `AGEING_BUCKET_ORDER`, `IST = ZoneInfo("Asia/Kolkata")`).
- **Imports**: standard library → third-party → local (`app.*`), each group alphabetized, one blank line
  between groups. No wildcard imports.
- **No bare `except:`.** Catch specific exceptions. Any exception that should become an HTTP error goes through
  `app/errors.py`'s handlers — routers raise `AppError` subclasses (or `fastapi.HTTPException` with a
  consistent `detail` shape matching `ErrorResponse`), they don't `try/except` and return ad hoc dicts.
- **No print() for debugging** in committed code — use `logging` (module-level `logger = logging.getLogger(__name__)`).
- **Docstrings**: one-line summary on every public function in `business_logic/` (these are the functions QA
  tests directly and other agents import — they need to be self-explanatory from the signature + docstring
  alone, without reading the implementation).
- **Dates**: always `datetime.date`, never `datetime.datetime`, for anything ageing-related. Always via the
  shared `get_today()` in `business_logic/ageing.py` — never a fresh `date.today()` call elsewhere. Tests
  monkeypatch/inject `today` rather than mocking the clock — see AGENT_PROMPT_QA.md.

## 2. TypeScript (frontend/)

- **Formatting**: `prettier` defaults.
- **Naming**: `camelCase` for variables/functions, `PascalCase` for components/types/interfaces, files for
  components are `PascalCase.tsx`, everything else `camelCase.ts`.
- **Typing**: `strict: true` in `tsconfig.json`. No `any`. API responses are typed via `api/types.ts`
  (API_SPEC.md §0) — components never inline-type a fetch response.
- **No inline fetch() calls in components.** All network access goes through `api/client.ts`. Components call
  `getInvoices(...)`, not `fetch("/api/invoices")` directly — this is what lets Backend's endpoint details
  change without touching component code.
- **State**: local component state (`useState`) is fine for this scope; no global state library needed for a
  single-page portal.

## 3. Error handling contract (cross-cutting)

Every error response, from every endpoint, is `ErrorResponse` (API_SPEC.md §0). Error codes used across the
app (add here if you introduce a new one — don't invent ad hoc strings in individual routers):

| `error` code | HTTP status | Meaning |
|---|---|---|
| `INVALID_FILE_TYPE` | 400 | Upload wasn't `.xlsx` |
| `MISSING_COLUMNS` | 400 | Sheet is missing a required column |
| `PARSE_ERROR` | 400 | Sheet present but unreadable/corrupt |
| `CUSTOMER_NOT_FOUND` | 404 | `customer_key` doesn't exist in the store |
| `NO_DATA_UPLOADED` | 409 | Any read endpoint called before an upload has happened |
| `VALIDATION_ERROR` | 422 | Query/path param failed validation (FastAPI's default, re-wrapped into `ErrorResponse` shape via a global exception handler) |

## 4. WhatsApp message formatting rules (Business Logic + WhatsApp agents)

- Bold: single asterisks `*like this*`. **Never** `**double asterisks**` (that's Markdown, not WhatsApp's
  formatting — the reference mockups are HTML email and must be translated, not copied literally).
- Italics: single underscores `_like this_`, used sparingly (e.g. for the closing signature line).
- No HTML, no tables. Task 2's mockup table becomes aligned plain text using fixed-width label columns and
  line breaks — not literal box-drawing characters (renders inconsistently across WhatsApp clients).
- Currency: `₹` prefix, Indian digit grouping (`₹1,23,456`, not `₹123,456`). Write one shared formatter
  (`business_logic/render.py::format_inr()`) — do not let two agents hand-roll two different comma-grouping
  implementations.
- Dates in messages: `DD-Mon-YYYY` (e.g. `04-Jul-2026`), matching the reference mockups — not ISO format.
- Line length: no hard wrapping needed (WhatsApp wraps client-side), but keep logical sections separated by
  blank lines for readability, matching the paragraph structure of the reference mockups.

## 5. Commit hygiene (loose, but keep it sane)

One agent's work should be reviewable as a roughly self-contained diff. Prefix commits with the track name,
e.g. `[backend] add upload endpoint`, `[business-logic] ageing bucket computation`, `[qa] edge case tests for
NO_DUE_DATE`. Not enforced by tooling — just keeps the Integration step sane.