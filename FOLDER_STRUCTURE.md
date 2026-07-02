# FOLDER_STRUCTURE.md

Monorepo, two top-level app folders. Every agent creates files **only** inside their designated paths below —
this is what makes parallel work mergeable. If a file isn't listed here and you need it, add it under your own
track's folder, not a shared one, unless it's explicitly a shared file (marked below).

```
procwing-collections-agent/
├── README.md                       ← final deliverable, written last (Integration step)
├── PROJECT_SPEC.md                 ← (this spec pack, kept in repo root for reference)
├── API_SPEC.md
├── DATABASE_SCHEMA.md
├── FOLDER_STRUCTURE.md
├── CODING_STANDARDS.md
├── INTEGRATION_CHECKLIST.md
├── sample_output/                  ← QA agent
│   ├── customer_1_payment_schedule.txt
│   ├── customer_1_collection_followup.txt
│   ├── customer_2_payment_schedule.txt
│   ├── customer_2_collection_followup.txt
│   ├── customer_3_payment_schedule.txt
│   └── customer_3_collection_followup.txt
│
├── backend/                        ← Backend agent (+ Business Logic agent, own subfolder) + WhatsApp agent
│   ├── requirements.txt
│   ├── .env.example                ← TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_NUMBER
│   ├── data/
│   │   ├── store.json              ← generated at runtime, gitignored; commit a .gitkeep instead
│   │   └── dummy-invoice-sheet.xlsx ← copy of the provided sample data, for quick local testing
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 ← FastAPI() app, router registration, CORS config      [Backend]
│   │   ├── config.py                ← settings (env vars, timezone constant)               [Backend]
│   │   ├── errors.py                ← ErrorResponse model + exception handlers             [Backend]
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   └── schemas.py          ← ALL Pydantic models from API_SPEC.md, in one file      [Backend]
│   │   ├── storage/
│   │   │   ├── __init__.py
│   │   │   └── store.py            ← load/save store.json, in-memory cache, thread-safety   [Backend]
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── upload.py           ← POST /api/upload                                      [Backend]
│   │   │   ├── invoices.py         ← GET /api/invoices, /api/invoices/summary               [Backend]
│   │   │   ├── customers.py        ← GET /api/customers, /resolve, /payment-schedule,
│   │   │   │                          /collection-followup, /whatsapp-preview               [Backend]
│   │   │   ├── whatsapp.py         ← POST /api/whatsapp/webhook                             [WhatsApp]
│   │   │   └── health.py           ← GET /api/health                                        [Backend]
│   │   └── business_logic/
│   │       ├── __init__.py
│   │       ├── ageing.py           ← bucket/days_overdue/is_due_this_week, week window      [Business Logic]
│   │       ├── customer_key.py     ← normalization from DATABASE_SCHEMA.md §2               [Business Logic]
│   │       ├── matching.py         ← rapidfuzz-based resolve_customer_name()                [Business Logic]
│   │       ├── reports.py          ← get_payment_schedule(), get_collection_followup()      [Business Logic]
│   │       └── render.py           ← render_payment_schedule_message(),
│   │                                  render_collection_followup_message()                  [Business Logic]
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py             ← shared fixtures (loads sample sheet, fixes `today`)    [QA]
│       ├── test_ageing.py                                                                    [QA]
│       ├── test_matching.py                                                                  [QA]
│       ├── test_reports.py                                                                   [QA]
│       ├── test_api_upload.py                                                                [QA]
│       ├── test_api_customers.py                                                              [QA]
│       └── test_whatsapp_webhook.py                                                          [QA]
│
└── frontend/                       ← Frontend agent
    ├── package.json
    ├── vite.config.ts              ← includes /api proxy to http://localhost:8000
    ├── tsconfig.json
    ├── index.html
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── api/
        │   ├── types.ts            ← TS interfaces from API_SPEC.md §0                      [Frontend]
        │   └── client.ts           ← fetch wrappers, snake_case→camelCase conversion         [Frontend]
        ├── components/
        │   ├── UploadPanel.tsx
        │   ├── BucketTabs.tsx
        │   ├── SearchBox.tsx
        │   └── InvoiceTable.tsx
        └── pages/
            └── PortalPage.tsx
```

## Rules that keep this mergeable

1. **`app/business_logic/` has zero imports from `app/routers/` or FastAPI.** Pure Python + `rapidfuzz` +
   stdlib `datetime`. This is what lets QA unit-test it without spinning up a server, and lets Business Logic
   ship before Backend's routing is done.
2. **`app/routers/whatsapp.py` is the only file the WhatsApp agent touches inside `backend/`.** It imports from
   `app.business_logic` and `app.storage`, same as any other router — it does not get its own copy of ageing
   or matching logic.
3. **`app/models/schemas.py` is the single file every Pydantic model lives in.** Don't scatter models across
   routers — API_SPEC.md maps 1:1 onto this file, so anyone can diff the two.
4. Frontend never imports anything from `backend/`. It only knows `API_SPEC.md`.
5. `data/store.json` is runtime-generated and gitignored. `data/dummy-invoice-sheet.xlsx` is committed so
   `POST /api/upload` is testable without the grader needing to locate the original file.