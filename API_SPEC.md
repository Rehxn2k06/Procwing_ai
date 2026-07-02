# API_SPEC.md — Contract between Backend, Frontend, Business Logic, WhatsApp

This is the single source of truth for every request/response shape. Backend implements it in Pydantic;
Frontend implements matching TypeScript interfaces by hand (no shared codegen — two languages). **Field names,
casing, and nullability below are final.** If an agent needs a field that isn't here, that's an integration
conflict — resolve it in this file, not by improvising in code.

Base URL: `http://localhost:8000/api` (backend). Frontend dev server proxies `/api/*` to this.

All JSON. All monetary fields are numbers (INR, no currency symbol, 2 decimal places max — formatting for
display, e.g. `₹1,23,456`, happens only in Frontend/WhatsApp render layers, never in API payloads).

All dates are ISO 8601 strings (`"YYYY-MM-DD"`) or `null`. No datetimes — invoice dates have no time component.

---

## 0. Shared types

### `Invoice` (raw + computed)

```jsonc
{
  "id": "string",                 // stable id, generated at upload time (uuid4)
  "customer_raw": "string",       // exactly as it appeared in the sheet
  "customer_key": "string",       // normalized (see DATABASE_SCHEMA.md §2) — use this to group/match
  "spoc": "string",
  "invoice_no": "string",
  "invoice_date": "YYYY-MM-DD | null",
  "due_date": "YYYY-MM-DD | null",        // null = the deliberate missing-due-date edge case
  "inv_amount": 0.0,
  "received": 0.0,
  "outstanding": 0.0,
  "ageing_bucket": "NOT_DUE | 0-15 | 16-30 | 31-60 | 61-90 | 90+ | NO_DUE_DATE",  // computed, not stored
  "days_overdue": "int | null",           // computed; null if NOT_DUE or NO_DUE_DATE
  "is_due_this_week": "boolean"           // computed; always false if NO_DUE_DATE
}
```

TypeScript:
```ts
export type AgeingBucket = "NOT_DUE" | "0-15" | "16-30" | "31-60" | "61-90" | "90+" | "NO_DUE_DATE";

export interface Invoice {
  id: string;
  customerRaw: string;
  customerKey: string;
  spoc: string;
  invoiceNo: string;
  invoiceDate: string | null;
  dueDate: string | null;
  invAmount: number;
  received: number;
  outstanding: number;
  ageingBucket: AgeingBucket;
  daysOverdue: number | null;
  isDueThisWeek: boolean;
}
```
> Note the casing shift: backend JSON keys are `snake_case` (Pydantic default), frontend TS interfaces are
> `camelCase`. Frontend's API client layer (`frontend/src/api/client.ts`) is responsible for the one-time
> conversion at the fetch boundary. Do not leak snake_case into React components.

### `ErrorResponse`

```jsonc
{ "error": "string (machine-ish code, e.g. CUSTOMER_NOT_FOUND)", "message": "string (human readable)" }
```
Every non-2xx response uses this shape. FastAPI's default validation error format is NOT used directly —
wrap it (see CODING_STANDARDS.md §4).

---

## 1. `POST /api/upload`

Upload the AR sheet. Multipart form, field name `file`.

**Request**: `multipart/form-data`, one file, `.xlsx`.

**Response 200**:
```jsonc
{
  "customers_count": 25,
  "invoices_count": 500,
  "total_outstanding": 1234567.0,
  "warnings": [
    { "row": 143, "invoice_no": "INV-...", "issue": "missing_due_date" }
  ]
}
```

**Response 400** (`ErrorResponse`): wrong file type, unparseable sheet, missing required columns.

Behavior notes:
- Upload **replaces** the entire store (this is a single-sheet assignment tool, not incremental sync).
- Required columns: `Customer, SPOC, Invoice No, Invoice Date, Due Date, Inv Amount, Received, Outstanding`.
  Missing column → 400, don't guess.
- A row with a missing `Due Date` is not an error — it's parsed, stored with `due_date: null`, and listed in
  `warnings`.

---

## 2. `GET /api/invoices/summary`

Powers the bucket tabs (All, Not Due, 0-15, 16-30, 31-60, 61-90, 90+ Days) with counts + totals.

**Response 200**:
```jsonc
{
  "buckets": [
    { "bucket": "ALL", "count": 502, "total_outstanding": 2228055.13 },
    { "bucket": "NOT_DUE", "count": 261, "total_outstanding": 1299100.25 },
    { "bucket": "0-15", "count": 101, "total_outstanding": 7251235.4 },
    { "bucket": "16-30", "count": 57, "total_outstanding": 468312301.48 },
    { "bucket": "31-60", "count": 32, "total_outstanding": 983058630.62 },
    { "bucket": "61-90", "count": 8, "total_outstanding": 25371763.22 },
    { "bucket": "90+", "count": 42, "total_outstanding": 296669024155.0 },
    { "bucket": "NO_DUE_DATE", "count": 1, "total_outstanding": 12345.0 }
  ]
}
```
`ALL` includes `NO_DUE_DATE` rows in count/total. Order in the array is the display order of the tabs; Frontend
renders `ALL` first, `NO_DUE_DATE` last (only shown if count > 0), everything else in the order shown above.

---

## 3. `GET /api/invoices`

Filtered, searched invoice list — the table under the tabs.

**Query params**:
- `bucket` (optional, default `ALL`) — one of the `AgeingBucket` values or `ALL`
- `search` (optional) — case-insensitive substring match against `customer_raw` **or** `invoice_no`. (The brief
  mentions "PO" as a searchable field; the provided sheet has no PO column, so `search` covers customer name and
  invoice number only — documented as a known gap in README, not silently invented.)
- `page` (optional, default `1`), `page_size` (optional, default `50`, max `200`)

**Response 200**:
```jsonc
{
  "items": [ /* Invoice[] */ ],
  "total_count": 502,
  "page": 1,
  "page_size": 50
}
```

---

## 4. `GET /api/customers`

List of distinct customers for dropdowns/lookups.

**Response 200**:
```jsonc
{ "customers": [ { "customer_key": "abc", "display_name": "ABC Pvt Ltd", "spoc": "Rahul" } ] }
```
`display_name` = the most common raw form seen for that `customer_key` in the sheet (see DATABASE_SCHEMA.md §2
for tie-breaking rule). `spoc` = SPOC of the customer's most recent invoice by `invoice_date`.

---

## 5. `GET /api/customers/resolve`

Fuzzy-resolves free text to a customer. Used by the WhatsApp agent and directly testable on its own.

**Query params**: `query` (required, string)

**Response 200**:
```jsonc
{
  "matched": true,
  "customer_key": "abc",
  "display_name": "ABC Pvt Ltd",
  "confidence": 92.0,
  "candidates": [
    { "customer_key": "abc", "display_name": "ABC Pvt Ltd", "confidence": 92.0 },
    { "customer_key": "abc-industries", "display_name": "ABC Industries", "confidence": 61.0 }
  ]
}
```
If nothing clears the match threshold: `"matched": false, "customer_key": null, "display_name": null,
"confidence": 0, "candidates": [ /* top 3 below-threshold matches, for a helpful error message */ ]`.
Threshold and algorithm are defined once, in Business Logic — see AGENT_PROMPT_BUSINESS_LOGIC.md §2.

---

## 6. `GET /api/customers/{customer_key}/payment-schedule`

Task 1 data, structured (not text) — used by Frontend previews, QA, and internally by the WhatsApp renderer.

**Response 200**:
```jsonc
{
  "customer_key": "abc",
  "display_name": "ABC Pvt Ltd",
  "spoc": "Rahul",
  "overdue_amount": 35000.0,
  "due_this_week": 0.0,
  "total_outstanding": 35000.0,
  "ageing_breakdown": { "90+": 0.0, "61-90": 25000.0, "31-60": 0.0, "16-30": 0.0, "0-15": 10000.0, "overdue": 35000.0 },
  "invoices": [ { "invoice_no": "...", "due_date": "2026-06-10", "outstanding": 25000.0 } ],
  "no_due_date_count": 0,
  "no_due_date_total": 0.0
}
```
**Response 404** (`ErrorResponse`, `error: "CUSTOMER_NOT_FOUND"`) if `customer_key` doesn't exist. `overdue`
key inside `ageing_breakdown` is the sum of all overdue buckets — provided pre-summed so Frontend/WhatsApp
don't recompute it.

---

## 7. `GET /api/customers/{customer_key}/collection-followup`

Task 2 data, structured.

**Response 200**:
```jsonc
{
  "customer_key": "xyz",
  "display_name": "XYZ",
  "spoc": "Raj",
  "overdue_amount": 25000.0,
  "due_this_week": 0.0,
  "week_start": "2026-06-30",
  "week_end": "2026-07-04",
  "total_collection_target": 25000.0,
  "daily_breakdown": [
    { "label": "Overdue on 30-Jun-2026", "date": null, "amount": 25000.0 },
    { "label": "30-Jun-26", "date": "2026-06-30", "amount": 0.0 },
    { "label": "01-Jul-26", "date": "2026-07-01", "amount": 0.0 },
    { "label": "02-Jul-26", "date": "2026-07-02", "amount": 0.0 },
    { "label": "03-Jul-26", "date": "2026-07-03", "amount": 0.0 },
    { "label": "04-Jul-26", "date": "2026-07-04", "amount": 0.0 },
    { "label": "Total Dues By 04-Jul-2026", "date": null, "amount": 25000.0 }
  ],
  "invoices": [ { "invoice_no": "...", "due_date": "2026-06-10", "outstanding": 25000.0 } ]
}
```
`daily_breakdown` is always exactly 7 entries in this order: overdue-as-of-Monday, Mon, Tue, Wed, Thu, Fri,
total. Backend/Frontend/WhatsApp all just iterate this array — no day-of-week math outside Business Logic.

---

## 8. `GET /api/customers/{customer_key}/whatsapp-preview`

Convenience endpoint: returns the **exact rendered WhatsApp text** for a report, reusing the same Business
Logic render functions the WhatsApp webhook calls. Exists so QA can generate sample output via `curl`/script
without needing a live Twilio round-trip, and so the two rendering paths (webhook vs. this endpoint) can never
drift apart — they call the same function.

**Query params**: `type` — `payment_schedule | collection_followup` (required)

**Response 200**:
```jsonc
{ "message": "*Weekly Payment Reminder – ABC*\n\nDear Sir/Madam,\n..." }
```

---

## 9. `POST /api/whatsapp/webhook`

Twilio inbound message webhook. `application/x-www-form-urlencoded` (Twilio's format), key fields used:
`Body` (message text), `From` (sender's WhatsApp number, e.g. `whatsapp:+91...`).

**Response**: `200 OK`, `Content-Type: text/xml`, TwiML:
```xml
<Response><Message>...rendered message text...</Message></Response>
```
See AGENT_PROMPT_WHATSAPP.md for parsing/routing rules and the exact TwiML response helper.

If the message doesn't match either report-type intent, or the customer can't be resolved, still return `200`
with a TwiML message explaining the problem (never a raw 4xx to Twilio — Twilio retries/alerts on non-2xx,
which is the wrong behavior for "customer not found").

---

## 10. Health check

`GET /api/health` → `{ "status": "ok", "invoices_loaded": 502 }`. Trivial, but Frontend and QA both need
something to poll to confirm the backend is up before running against it.