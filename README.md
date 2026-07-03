# ProcWing WhatsApp AR Agent

An AI-powered Accounts Receivable (AR) ageing portal with a WhatsApp-based report delivery agent. Upload your AR Excel sheet, browse invoices by ageing bucket in the web portal, and send real-time payment schedule or collection follow-up reports to any customer via WhatsApp — all without leaving a chat window.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Project Structure](#project-structure)
3. [Prerequisites](#prerequisites)
4. [Quick Start](#quick-start)
   - [Backend Setup](#1-backend-setup)
   - [Frontend Setup](#2-frontend-setup)
5. [Twilio WhatsApp Setup](#twilio-whatsapp-setup)
   - [Sandbox Configuration](#sandbox-configuration)
   - [Exposing Localhost (ngrok / localtunnel)](#exposing-localhost)
   - [Testing on WhatsApp](#testing-on-whatsapp)
6. [API Reference](#api-reference)
7. [Report Types](#report-types)
8. [Configuration Reference](#configuration-reference)
9. [Known Limitations](#known-limitations)
10. [Development Notes](#development-notes)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  WhatsApp (User Phone)                                          │
│  "Payment schedule for Alpha Industries"                        │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTPS POST
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Twilio WhatsApp Sandbox                                        │
│  Forwards inbound message to your webhook URL                   │
└────────────────────────┬────────────────────────────────────────┘
                         │ POST /api/whatsapp/webhook
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Tunnel (ngrok / localtunnel)                                   │
│  Exposes localhost:8000 to the public internet                  │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  FastAPI Backend  (localhost:8000)                              │
│                                                                 │
│  ┌──────────────────┐  ┌───────────────────┐                   │
│  │ WhatsApp Router  │  │  Invoices Router  │                   │
│  │ Intent parsing   │  │  Customers Router │                   │
│  │ Fuzzy matching   │  │  Health Router    │                   │
│  └────────┬─────────┘  └────────┬──────────┘                   │
│           │                     │                               │
│           ▼                     ▼                               │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Business Logic (Pure Python, no FastAPI)               │   │
│  │  ├── ageing.py       — bucket computation, week window  │   │
│  │  ├── matching.py     — rapidfuzz customer resolution    │   │
│  │  ├── reports.py      — PaymentSchedule / CollectionFollowup│ │
│  │  └── render.py       — WhatsApp-formatted plain text    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────────────────┐                                   │
│  │  Storage (store.json)   │                                   │
│  │  In-memory + JSON file  │                                   │
│  └──────────────────────────┘                                   │
└─────────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  React Frontend  (localhost:5173)                               │
│  Upload AR Sheet → Browse Buckets → Search → Preview Reports   │
└─────────────────────────────────────────────────────────────────┘
```

### How a WhatsApp report request flows end-to-end:

1. User sends a message like `"Payment schedule for Alpha Industries"` to the Twilio sandbox number.
2. Twilio POSTs the message body to your configured webhook URL (`POST /api/whatsapp/webhook`).
3. The WhatsApp router **parses intent** (keyword: `payment`/`schedule` → payment schedule; `collection`/`followup` → collection follow-up).
4. It **strips filler words** to extract the candidate customer name (`"Alpha Industries"`).
5. Business Logic's **fuzzy matcher** (`rapidfuzz`) resolves the name against all loaded customers (threshold: 70/100). Matches → proceed; no match → "Did you mean: X, Y, Z?" reply.
6. The matched customer key is passed to `get_payment_schedule()` or `get_collection_followup()` which compute the report data from in-memory invoices.
7. `render_payment_schedule_message()` or `render_collection_followup_message()` formats it as WhatsApp-friendly plain text (`*bold*`, `_italics_`, line-breaks).
8. The router wraps the text in a TwiML `<Response><Message>...</Message></Response>` XML envelope and returns it in the HTTP 200 response.
9. Twilio delivers the message back to the user's WhatsApp.

---

## Project Structure

```
procwing-whatsapp-agent/
│
├── backend/                         # FastAPI application
│   ├── app/
│   │   ├── main.py                  # App factory, router registration, CORS
│   │   ├── config.py                # Settings, IST timezone, .env loading
│   │   ├── errors.py                # Global error handlers
│   │   ├── models/
│   │   │   └── schemas.py           # Pydantic response models
│   │   ├── routers/
│   │   │   ├── health.py            # GET /api/health
│   │   │   ├── upload.py            # POST /api/upload
│   │   │   ├── invoices.py          # GET /api/invoices, /api/invoices/summary
│   │   │   ├── customers.py         # GET /api/customers, /resolve, reports
│   │   │   └── whatsapp.py          # POST /api/whatsapp/webhook
│   │   ├── business_logic/          # Pure Python — no FastAPI imports
│   │   │   ├── ageing.py            # Bucket computation, week window
│   │   │   ├── customer_key.py      # Customer name normalisation
│   │   │   ├── matching.py          # Fuzzy customer name resolution
│   │   │   ├── reports.py           # Report data computation
│   │   │   └── render.py            # WhatsApp message formatting
│   │   └── storage/
│   │       └── store.py             # In-memory store + JSON persistence
│   ├── data/
│   │   └── store.json               # ← runtime-generated, gitignored
│   ├── requirements.txt
│   ├── .env.example                 # Template — copy to .env and fill in
│   └── .env                         # ← gitignored (your real credentials)
│
├── frontend/                        # React + TypeScript + Vite
│   ├── src/
│   │   ├── api/
│   │   │   ├── client.ts            # All fetch() calls, snake→camelCase
│   │   │   └── types.ts             # TypeScript interfaces from API spec
│   │   ├── components/
│   │   │   ├── UploadPanel.tsx      # Drag-and-drop xlsx upload
│   │   │   ├── BucketTabs.tsx       # Ageing bucket tab cards
│   │   │   ├── SearchBox.tsx        # Debounced customer/invoice search
│   │   │   └── InvoiceTable.tsx     # Paginated table + WhatsApp preview
│   │   ├── pages/
│   │   │   └── PortalPage.tsx       # Root page — owns all state
│   │   ├── utils/
│   │   │   └── formatCurrency.ts    # Indian Rupee formatting (₹1,23,456)
│   │   └── index.css                # Design tokens, global styles
│   ├── package.json
│   └── vite.config.ts               # /api proxy → localhost:8000
│
├── AGENT_TASKS/                     # Agent implementation briefs
├── API_SPEC.md                      # Full API contract
├── CODING_STANDARDS.md
├── DATABASE_SCHEMA.md
├── PROJECT_SPEC.md
└── dummy-invoice-sheet.xlsx         # Sample AR sheet for testing
```

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.10+ | Used for FastAPI backend |
| Node.js | 18+ | Used for Vite/React frontend |
| npm | 9+ | Comes with Node.js |
| Twilio account | Free | Sandbox is sufficient for testing |
| ngrok or localtunnel | Latest | Exposes localhost to Twilio |

---

## Quick Start

### 1. Backend Setup

```powershell
# Navigate to the backend directory
cd backend

# Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1      # Windows PowerShell
# source .venv/bin/activate      # macOS / Linux

# Install dependencies
pip install -r requirements.txt

# Create your .env file from the template
copy .env.example .env
# Edit .env and fill in your Twilio credentials (see Configuration section)

# Start the development server
uvicorn app.main:app --reload
```

The backend will start at **http://localhost:8000**.  
Interactive API docs: **http://localhost:8000/docs**

### 2. Frontend Setup

Open a **second terminal**:

```powershell
cd frontend

# Install dependencies (first time only)
npm install

# Start the Vite development server
npm run dev
```

The portal will open at **http://localhost:5173**.

> The Vite dev server proxies all `/api/*` requests to `http://localhost:8000` automatically — no CORS configuration needed during development.

### 3. Upload Your AR Sheet

1. Open **http://localhost:5173** in your browser.
2. Click the upload area or drag-and-drop your `.xlsx` AR sheet.
3. The dashboard will populate with your invoice data, grouped by ageing bucket.

---

## Twilio WhatsApp Setup

### Sandbox Configuration

The WhatsApp integration uses Twilio's free **WhatsApp Sandbox**, which requires no business account or Meta approval.

**One-time setup:**

1. Sign up at [twilio.com](https://twilio.com) (free account is sufficient).
2. In the Twilio Console, go to: **Messaging → Try it out → Send a WhatsApp message**.
3. You will see a sandbox number (usually `+1 415 523 8886`) and a **join keyword** (e.g., `join mountain-happened`).
4. From your WhatsApp, send the join message to the sandbox number:
   ```
   join mountain-happened
   ```
   You will receive a confirmation: *"You are all set! The sandbox can now send/receive messages..."*

### Exposing Localhost

Twilio needs a **public HTTPS URL** to reach your local backend. You must run a tunnel tool alongside your backend.

**Option A — localtunnel (no account needed):**
```powershell
npx localtunnel --port 8000
```
Output example: `your url is: https://happy-foxes-eat.loca.lt`

> ⚠️ **Important:** localtunnel assigns a new random URL every time it restarts. You must update the Twilio Sandbox setting every time. Occasionally, the tunnel page may also show a browser-bypass prompt — visit the URL once in a browser to clear it.

**Option B — ngrok (recommended for stability):**
1. Download the ngrok binary from [ngrok.com/download](https://ngrok.com/download).
2. Add your authtoken: `ngrok config add-authtoken <your-token>`
3. Start the tunnel:
   ```powershell
   .\ngrok http 8000
   ```
   ngrok shows a stable forwarding URL for the session.

### Connecting the Tunnel to Twilio

1. Copy your tunnel URL (e.g., `https://happy-foxes-eat.loca.lt`).
2. In the Twilio Console → **Messaging → Settings → WhatsApp Sandbox Settings**.
3. Set the **"When a message comes in"** field to:
   ```
   https://happy-foxes-eat.loca.lt/api/whatsapp/webhook
   ```
4. Ensure the method dropdown is set to **HTTP POST**.
5. Click **Save**.

**Verify the connection** before testing from WhatsApp:
```powershell
curl.exe https://happy-foxes-eat.loca.lt/api/health
# Expected: {"status":"ok","invoices_loaded":500}
```

### Testing on WhatsApp

With the backend running, data uploaded, and webhook configured — send any of these to the Twilio sandbox number from your registered WhatsApp:

| What to send | What you get back |
|---|---|
| `Hello` | Help message listing the two report types |
| `payment schedule Alpha` | Weekly Payment Reminder for the best-matching customer |
| `collection followup for Alpha Industries` | Weekly Collection Follow-up with daily breakdown |
| `payment schedule unknowncorp` | "Did you mean: X, Y, Z?" fuzzy suggestions |

> **Fuzzy matching:** You don't need the exact company name. The system uses `rapidfuzz` (token sort ratio, threshold 70/100) to resolve partial names, abbreviations, and common suffix variants like `Pvt` ↔ `Private Limited`.

---

## API Reference

All endpoints are prefixed with `/api`. Full spec: [`API_SPEC.md`](API_SPEC.md).

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Service health + invoice count |
| `POST` | `/api/upload` | Upload `.xlsx` AR sheet (multipart) |
| `GET` | `/api/invoices` | Paginated invoice list with bucket/search filters |
| `GET` | `/api/invoices/summary` | Bucket-level counts and totals for tab UI |
| `GET` | `/api/customers` | List of distinct customers |
| `GET` | `/api/customers/resolve?query=...` | Fuzzy-resolve a name to a customer key |
| `GET` | `/api/customers/{key}/payment-schedule` | Structured payment schedule data |
| `GET` | `/api/customers/{key}/collection-followup` | Structured collection follow-up data |
| `GET` | `/api/customers/{key}/whatsapp-preview?type=...` | Rendered WhatsApp message text (for portal preview) |
| `POST` | `/api/whatsapp/webhook` | Twilio inbound webhook — returns TwiML |

---

## Report Types

### Task 1 — Weekly Payment Schedule
Sent when the user messages: `"payment schedule for <customer>"`

Includes:
- Total outstanding and overdue amounts
- Ageing breakdown (0–15 d, 16–30 d, 31–60 d, 61–90 d, 90+ d)
- First 7 invoices listed individually (+ count of remaining)
- Note on any invoices with no due date

### Task 2 — Weekly Collection Follow-up
Sent when the user messages: `"collection followup for <customer>"`

Includes:
- Overdue balance as of Monday of the current week
- Day-by-day breakdown (Monday → Friday) of amounts due
- Total collection target for the week
- First 7 outstanding invoices listed individually

> Both report types are also accessible in the web portal via the 💬 button in the invoice table. The portal's preview tab shows the exact text that will be delivered on WhatsApp.

---

## Configuration Reference

Copy `backend/.env.example` to `backend/.env` and fill in:

```env
# Twilio credentials — obtain from https://console.twilio.com
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
```

> **Note on credentials:** For the WhatsApp Sandbox, the system uses **inline TwiML replies** (the HTTP response body itself). This means Twilio credentials are **not required** for the webhook to function — the bot works without them. The `.env` fields are reserved for future use of the Twilio REST API (e.g. proactively sending scheduled reports).

---

## Known Limitations

| Limitation | Detail |
|---|---|
| **Twilio Sandbox message limit** | Sandbox enforces a ~1,600 character limit per message. Reports are capped at 7 invoice line items + a "...and X more" summary to stay within this limit. |
| **In-memory storage** | Uploaded invoice data is stored in memory and persisted to `backend/data/store.json`. Restarting the backend reloads from this file. Data is replaced entirely on each upload. |
| **localtunnel instability** | The `localtunnel` URL changes on every restart and can drop silently. For extended testing sessions, use `ngrok` with an authtoken for a stable session URL. |
| **Single-file upload** | Each upload replaces the entire dataset. There is no incremental merge — re-upload the full AR sheet each week. |
| **Sandbox number shared** | Twilio Sandbox numbers are shared across accounts. Your sandbox join-code must be re-sent if Twilio rotates it. |

---

## Development Notes

**Running all three processes simultaneously:**

```
Terminal 1 (backend):   cd backend && uvicorn app.main:app --reload
Terminal 2 (frontend):  cd frontend && npm run dev
Terminal 3 (tunnel):    npx localtunnel --port 8000
```

**Business Logic is fully testable in isolation:**
```python
from app.business_logic.reports import get_payment_schedule
from app.business_logic.ageing import InvoiceRecord
from datetime import date

invoices = [
    InvoiceRecord(
        id="1", customer_raw="Test Co", customer_key="test co",
        spoc="Alice", invoice_no="INV-001",
        invoice_date=date(2026, 5, 1), due_date=date(2026, 6, 1),
        inv_amount=100000, received=0, outstanding=100000
    )
]
schedule = get_payment_schedule("test co", invoices, date(2026, 7, 4))
print(schedule.overdue_amount)  # 100000.0
```

**Adding a third report type:**  
1. Add `get_x_report()` to `business_logic/reports.py`
2. Add `render_x_message()` to `business_logic/render.py`
3. Add the intent keyword → function mapping in `app/routers/whatsapp.py`
