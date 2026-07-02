# INTEGRATION_CHECKLIST.md

Run through this in order once all five agents have delivered. Most steps are cheap to check and catch the
class of bug that only shows up when independently-built pieces meet for the first time.

## 1. Merge order

Merge in this order — each step is easier to verify if the previous one is already green:

1. **Business Logic** first (no dependencies on anyone else).
2. **Backend**, swapping its local stubs for real `from app.business_logic import ...` imports. This is the
   moment to grep Backend's code for `# TODO(business-logic)` markers and delete every one.
3. **QA**'s test suite, run against the real merged Backend + Business Logic.
4. **WhatsApp**'s router, registered into `app.main`.
5. **Frontend**, pointed at the real running Backend (not any mock it may have used standalone).

## 2. Contract-drift check (do this before running anything)

`diff`-style read-through, not code review:

- [ ] Every field name in `app/models/schemas.py` matches `API_SPEC.md` §0 exactly (spot-check: did Backend
      accidentally use `dueDate` instead of `due_date` anywhere, or vice versa?).
- [ ] Every field name in `frontend/src/api/types.ts` matches `API_SPEC.md` §0's TS block exactly.
- [ ] Business Logic's actual function signatures match what `AGENT_PROMPT_BACKEND.md`/`AGENT_PROMPT_WHATSAPP.md`
      assumed when they wrote their stub calls — if Business Logic changed a parameter name or return shape
      independently, this is the moment it surfaces, not at runtime.
- [ ] `format_inr()` and `format_date_ddmonyyyy()` are defined exactly once (in `business_logic/render.py`) —
      grep for a second implementation in Frontend or WhatsApp code; delete it and import the real one if
      Frontend needs currency formatting too (Frontend has its own `formatCurrency.ts` by design — that's fine,
      it's a display concern, not a computation one; just confirm both produce identical output on the same
      input, e.g. `123456 → ₹1,23,456` in both).

## 3. Boot sequence

```bash
cd backend && pip install -r requirements.txt && cp .env.example .env
uvicorn app.main:app --reload --port 8000
```
```bash
cd frontend && npm install && npm run dev
```
- [ ] Backend boots with zero data, `GET /api/health` → `invoices_loaded: 0`.
- [ ] Frontend loads, upload panel visible, no console errors before any upload.

## 4. End-to-end data path

- [ ] Upload `dummy-invoice-sheet.xlsx` through the **Frontend UI** (not curl) — confirms the multipart
      request from React actually reaches FastAPI correctly.
- [ ] Bucket tabs populate with non-zero counts across at least 5 of the 7 buckets.
- [ ] Search box filters correctly for a known customer name and a known invoice number.
- [ ] Pick the "everything not due" customer and the "every bucket" customer (identify these from the sheet
      first) and spot-check their tab totals against a manual sum in Excel/pandas — this is the actual
      correctness check the brief's #1 evaluation criterion is about; don't skip it.

## 5. WhatsApp path

- [ ] `ngrok http 8000` (or equivalent), sandbox webhook URL updated, join code sent from a real phone.
- [ ] Send a well-formed payment-schedule request for a real customer — reply arrives, renders correctly on
      an actual phone screen (check line breaks and bold rendering look right, not just that the string is
      correct).
- [ ] Send the same customer name with wrong casing/suffix — same result (fuzzy matching working end-to-end,
      not just in Business Logic's unit tests).
- [ ] Send a nonsense message — get a helpful reply, not silence or a Twilio-visible error.

## 6. Test suite

```bash
cd backend && pytest tests/ -v
```
- [ ] All green. If anything's red, the fix belongs to whichever agent owns that code (per
      `FOLDER_STRUCTURE.md`'s ownership table) — QA documents the failure, doesn't silently fix Business Logic's
      or Backend's code themselves, so the "who wrote this bug" trail stays clean for review.

## 7. Third-report-type sanity check (evaluation criterion — do this even though no third type is required)

Without writing real code, walk through: "if I had to add a 'monthly statement' report right now, what would I
touch?" Expected answer: one new function in `business_logic/reports.py`, one new function in
`business_logic/render.py`, one new route in `customers.py`, one new keyword branch in `whatsapp.py`'s intent
parser. If the honest answer involves touching `ageing.py`, `matching.py`, or the storage layer, that's a
structural problem worth fixing before submission, not after.

## 8. Final deliverables assembly

- [ ] `README.md` written at repo root: how to run both apps, how to set up the Twilio sandbox (pull directly
      from `AGENT_PROMPT_WHATSAPP.md`'s setup section), explicit list of assumptions (search covers
      customer/invoice-no only, not PO; single-worker/in-memory store assumption; anything else that came up
      during integration), explicit "out of scope" list (auth, multi-sheet history, persistence beyond a single
      JSON file).
- [ ] `sample_output/` contains the 6+ `.txt` files from QA, generated from the real sheet.
- [ ] Zip the whole repo (excluding `node_modules/`, `__pycache__/`, `data/store.json`, `.env`) and email to
      `rahulkhapre@procwing.ai` before Saturday, 4 July 2026, 12:00 PM.
