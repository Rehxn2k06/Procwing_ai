# DATABASE_SCHEMA.md — Data model & storage

No database server. Storage is a single JSON file, loaded fully into memory at process start and rewritten
wholesale on each `POST /api/upload`. This is deliberate for a 500-row, 3-day assignment.

## 1. File location & shape

`backend/data/store.json`

```jsonc
{
  "uploaded_at": "2026-07-01T10:00:00+05:30",
  "source_filename": "dummy-invoice-sheet.xlsx",
  "invoices": [
    {
      "id": "b3f1...",              // uuid4, generated at parse time — stable for the life of this upload
      "customer_raw": "ABC Pvt Ltd",
      "customer_key": "abc",
      "spoc": "Rahul",
      "invoice_no": "INV-1001",
      "invoice_date": "2026-05-01",  // or null
      "due_date": "2026-06-10",      // or null — the deliberate missing-due-date edge case
      "inv_amount": 50000.0,
      "received": 25000.0,
      "outstanding": 25000.0
    }
  ]
}
```

**Only raw + normalized-key fields are persisted.** `ageing_bucket`, `days_overdue`, `is_due_this_week` are
**never written to this file** — they are computed by Business Logic every time invoices are read, using
`today`. Storing them would make the data silently wrong the day after upload.

## 2. Customer key normalization

`customer_key` is computed once at upload time and stored (it's a data-cleaning step, not a date-dependent
computation, so persisting it is fine and avoids re-normalizing on every read).

Algorithm (implemented once, in Business Logic, imported by the upload parser):

1. Lowercase.
2. Strip a fixed list of trailing/leading suffix noise: `pvt ltd`, `private limited`, `- customer`, `ltd`,
   `limited`, `inc`, `llp` (case-insensitive, matched as whole trailing tokens after removing punctuation).
3. Remove punctuation (`.`, `,`, `-`, `&` → space), collapse repeated whitespace, strip leading/trailing space.
4. Result is the `customer_key`. Example: `"ABC - Customer Pvt. Ltd."` → `"abc"`.

**Grouping rule**: two rows are the same customer if their `customer_key` matches exactly after this
normalization. `display_name` (used in API responses) is the most frequently occurring `customer_raw` for that
key; ties broken by first occurrence in the sheet (stable, deterministic — don't use a hash-based tiebreak).

This same normalization function is what `GET /api/customers/resolve` fuzzy-matches against — see
AGENT_PROMPT_BUSINESS_LOGIC.md §2 for the fuzzy layer on top of it.

## 3. Computed fields — exact formulas

All computed at read time against `today` (IST, date only — see PROJECT_SPEC.md §7).

### `ageing_bucket` (per invoice)

```
if due_date is None:                         → "NO_DUE_DATE"
elif due_date >= today:                       → "NOT_DUE"
else:
    days_overdue = (today - due_date).days    # always >= 1 here
    if   1  <= days_overdue <= 15:  → "0-15"
    elif 16 <= days_overdue <= 30:  → "16-30"
    elif 31 <= days_overdue <= 60:  → "31-60"
    elif 61 <= days_overdue <= 90:  → "61-90"
    else:                            → "90+"      # days_overdue >= 91
```

### `days_overdue` (per invoice)
`None` unless bucket is one of the overdue buckets; otherwise the integer computed above.

### `is_due_this_week` (per invoice)
`due_date is not None and week_start <= due_date <= week_end`, where `week_start`/`week_end` are the Monday and
Friday of the ISO week containing `today` (see §4). A `due_date` in the past that also happens to be earlier
this week still counts as "due this week" **and** counts as overdue — the two are not mutually exclusive; the
brief's Task 2 breakdown separates "Overdue-as-of-Monday" from "amount falling due that day" precisely so this
doesn't double-count in the *breakdown*, but `is_due_this_week` as a flag on the invoice is still true in that
case. Don't "fix" this by making them mutually exclusive — the reference mockups don't.

### Customer-level aggregates (`overdue_amount`, `due_this_week`, `total_outstanding`, `ageing_breakdown`)
Straightforward sums of `outstanding` over that customer's invoices, grouped by the per-invoice fields above.
`total_outstanding` includes `NO_DUE_DATE` rows; `overdue_amount` and `due_this_week` do not (see §5).

### Weekly breakdown (Task 2, `daily_breakdown`)
- `"Overdue on {Monday's date}"` = sum of `outstanding` where `due_date < week_start` (i.e. overdue as of the
  start of this week — a snapshot, computed the same way as `overdue_amount` but pinned to `week_start` rather
  than `today`, so it doesn't shift if you query it Wednesday vs. Friday of the same week).
- Each of the 5 weekday entries = sum of `outstanding` where `due_date == that specific date`.
- `"Total Dues By {Friday's date}"` = `Overdue on Monday` + sum of the 5 daily entries.

## 4. "Current week" definition

ISO week containing `today`: `week_start = today - timedelta(days=today.isoweekday() - 1)` (Monday),
`week_end = week_start + timedelta(days=4)` (Friday). If `today` itself is a Saturday or Sunday, the "current
week" is still the Mon–Fri that already passed within this calendar week — do not roll forward to next week.

## 5. Edge cases — explicit handling (all four from the brief)

| Case | Handling |
|---|---|
| Customer with everything not due | `overdue_amount = 0`, all overdue ageing buckets `0`, `due_this_week` may be `> 0`. Reports still render normally — no special-casing in the message template, just zeros. |
| Fully-paid customer (zero outstanding) | Still resolves and returns a valid report; all amounts `0`, `invoices` list may be empty or show fully-received invoices at `outstanding: 0` (keep them in the list — don't filter them out, the sheet keeps the row). |
| Customer spanning every ageing bucket | No special handling needed — falls out of the formulas above. Used as a QA sample case specifically because it exercises every branch. |
| Invoice with missing Due Date | `due_date: null`, `ageing_bucket: "NO_DUE_DATE"`, excluded from `overdue_amount`/`due_this_week`/`ageing_breakdown`, **included** in `total_outstanding`, surfaced in `upload` response `warnings` and via `no_due_date_count`/`no_due_date_total` on the payment-schedule response so it's never silently dropped. |

## 6. Excel parsing notes (for Backend agent)

- Use `openpyxl` via `pandas.read_excel` (already a `pandas` dependency is reasonable; don't add a second xlsx
  library).
- Column headers must match exactly: `Customer, SPOC, Invoice No, Invoice Date, Due Date, Inv Amount, Received,
  Outstanding`. Trim whitespace on header read, but don't fuzzy-match headers — that's a different problem from
  fuzzy customer names and out of scope.
- `Invoice Date`/`Due Date` cells: pandas will typically parse these as `Timestamp` or `NaT`. Convert `NaT` →
  `None` → serializes to `null`. Convert `Timestamp` → `date` → `"YYYY-MM-DD"` string. Never leave a pandas
  `Timestamp` object in a response — this is a common source of `TypeError: not JSON serializable`.