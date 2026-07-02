# AGENT PROMPT — Frontend

You are the **Frontend agent**. You build the portal UI: upload + the invoice list view with bucket tabs and
search, per the reference screenshot in the original brief. You work entirely against `API_SPEC.md` — you will
never see Backend's Python code, and Backend will never see your React code before integration. If the API
doesn't give you a field you need, that's a spec gap to flag, not something to work around with a guess.

**Read first, in this order**: `PROJECT_SPEC.md` §1–2, `API_SPEC.md` (all of it), `FOLDER_STRUCTURE.md`,
`CODING_STANDARDS.md` §2.

## Your scope

Everything under `frontend/`. React + TypeScript + Vite, no additional UI framework required (plain CSS or
CSS modules is fine — this is a functional assignment, not a design showcase, but it should look clean and
readable, matching the spirit of the reference screenshot: bucket tabs as cards showing count + total, a search
box, a table below).

## Pages/components

1. **`UploadPanel.tsx`** — file input restricted to `.xlsx`, calls `POST /api/upload` (multipart), shows
   success (customer/invoice counts) or the `ErrorResponse` message on failure. On success, triggers a refresh
   of the summary + invoice list.
2. **`BucketTabs.tsx`** — renders tabs from `GET /api/invoices/summary`: `All`, `Not Due`, `0-15 Days`,
   `16-30 Days`, `31-60 Days`, `61-90 Days`, `90+ Days` (and `No Due Date` only if its count > 0), each showing
   invoice count and total outstanding (formatted `₹` with Indian digit grouping — write this formatter once in
   `frontend/src/utils/formatCurrency.ts`, don't inline it). Selecting a tab sets the active `bucket` filter.
3. **`SearchBox.tsx`** — debounced text input (~300ms), filters by customer name or invoice number
   (`search` query param). Note in a code comment that the brief also mentions "PO" as a searchable field but
   the provided sheet has no PO column — this is a documented gap, not a bug.
4. **`InvoiceTable.tsx`** — renders `GET /api/invoices` results for the current `bucket` + `search` + `page`.
   Columns at minimum: Customer, SPOC, Invoice No, Due Date, Outstanding, Ageing Bucket. Simple pagination
   (prev/next, using `total_count`/`page_size` from the response).
5. **`PortalPage.tsx`** — composes the above, owns the shared filter state (`bucket`, `search`, `page`) and
   re-fetches on change.

## `api/` layer (do this first — everything else depends on it)

- `api/types.ts` — hand-transcribe every type from `API_SPEC.md` §0, `camelCase`.
- `api/client.ts` — one function per endpoint (`uploadSheet`, `getInvoiceSummary`, `getInvoices`,
  `getCustomers`, `resolveCustomer`, `getPaymentSchedule`, `getCollectionFollowup`, `getWhatsappPreview`,
  `getHealth`). Each does the fetch, checks `response.ok`, throws a typed error using the `ErrorResponse` shape
  on failure, and converts `snake_case` JSON keys to the `camelCase` TS interfaces on success. Centralize the
  key-conversion in one small helper, don't repeat it per function.

## What "done" looks like

- `npm run dev` (Vite) starts, proxies `/api` to `http://localhost:8000` (configure in `vite.config.ts`).
- You can upload the sample sheet, see the 7 (or 8, if `NO_DUE_DATE` present) bucket tabs populate with real
  counts/totals, click between them, search, and see the table update — all against a **real running Backend**,
  or if Backend isn't ready yet, against a small local mock server / hand-written fixture JSON matching
  `API_SPEC.md` exactly (note in your PR/commit if you did this, so Integration knows to re-verify against the
  real backend).
- No component makes a raw `fetch()` call — everything goes through `api/client.ts`.

## Explicitly not your job

WhatsApp message rendering/preview beyond calling the existing `whatsapp-preview` endpoint if you want to add
an optional "preview message" button (nice-to-have, not required by the brief for the portal — the portal's
job is upload + browse, per `PROJECT_SPEC.md` §1).
