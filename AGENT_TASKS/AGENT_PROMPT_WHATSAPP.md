# AGENT PROMPT — WhatsApp

You are the **WhatsApp agent**. You own exactly one file's worth of behavior: turning an inbound WhatsApp
message into a routed call to Business Logic's report functions, and sending the rendered text back. You do
not compute ageing, do not fuzzy-match by hand, and do not format currency — all of that is Business Logic's
job; you call it.

**Read first, in this order**: `PROJECT_SPEC.md` §1, §4, `API_SPEC.md` §5, §6, §7, §9, `AGENT_PROMPT_BUSINESS_LOGIC.md`
(you depend entirely on the functions it defines).

## Your scope

`backend/app/routers/whatsapp.py` only. (You may also need a small `backend/app/whatsapp_client.py` helper for
constructing the Twilio reply — see below — that's fine, keep it adjacent.)

## Twilio sandbox setup (document this in your section of README)

1. Sign up for Twilio, activate the WhatsApp Sandbox (Console → Messaging → Try it out → WhatsApp).
2. Note the sandbox number and join code; testers join by sending the join code to the sandbox number from
   their own WhatsApp.
3. Set the sandbox's "When a message comes in" webhook to `POST https://<your-tunnel>/api/whatsapp/webhook`
   (use `ngrok` or similar for local dev — document the exact command in README, e.g.
   `ngrok http 8000`).
4. Env vars (already declared in `backend/.env.example` by Backend agent): `TWILIO_ACCOUNT_SID`,
   `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_NUMBER`. You only need these if you choose to reply via the Twilio
   REST API instead of inline TwiML — for the sandbox, **inline TwiML is simpler and sufficient** (no SID/token
   needed to reply within the same webhook request). Use TwiML unless you have a specific reason not to.

## Intent parsing

Inbound `Body` text is free-form, e.g.:
- `"Give me a weekly payment schedule for ABC"`
- `"weekly collection follow-up for XYZ Pvt Ltd"`
- `"payment schedule ABC"` (looser phrasing should still work — don't require the exact brief wording)

Approach:
1. Lowercase the body.
2. Determine report type by keyword presence: `"collection"` or `"follow-up"`/`"followup"` → collection
   followup; `"payment"` or `"schedule"` (and not "collection") → payment schedule. If both or neither keyword
   set is found, ask for clarification (see error replies below) rather than guessing.
3. Extract the customer name: strip the recognized intent keywords and common filler words (`give`, `me`, `a`,
   `weekly`, `for`, `the`) from the body, what remains is the candidate customer name string. This is
   deliberately simple (not full NLP) — the fuzzy matching in Business Logic is what absorbs the imprecision,
   not the keyword stripping.
4. Call `business_logic.matching.resolve_customer_name(candidate_name, customers)`.
5. If `matched: true`, call the corresponding `business_logic.reports.get_x_report()` then
   `business_logic.render.render_x_message()`, reply with the result.
6. If `matched: false`, reply listing the top candidates from `MatchResult.candidates` as a "did you mean: X,
   Y, Z?" plain-text message — still a `200`/valid TwiML response, never a raw error to the user.

## Reply construction

```python
from fastapi.responses import Response

def twiml_reply(message: str) -> Response:
    xml = f"<?xml version='1.0' encoding='UTF-8'?><Response><Message>{escape(message)}</Message></Response>"
    return Response(content=xml, media_type="text/xml")
```
(Use `xml.sax.saxutils.escape` or equivalent — WhatsApp message text can contain `&`/`<`/`>` from customer
names or currency formatting and must be XML-escaped.)

## Error replies (all still HTTP 200 + valid TwiML — see API_SPEC.md §9)

| Situation | Reply text |
|---|---|
| No recognizable intent keyword | Short help message explaining the two supported query formats with an example of each |
| Intent recognized, no customer name extracted | Ask them to name a customer |
| Customer not resolved (`matched: false`) | "Couldn't find a customer matching '{name}'. Did you mean: {candidates}?" |
| Any unexpected exception | Generic apologetic message + log the full exception server-side (`logging`, not printed) — never leak a stack trace to WhatsApp |

## What "done" looks like

Sending both example messages above (and a deliberately misspelled/suffix-varied customer name) to the sandbox
number produces correctly formatted WhatsApp replies matching the reference mockups' content, using real data
from an uploaded sheet. You've tested this against a real Twilio sandbox round-trip at least once, not just
against `GET /api/customers/{key}/whatsapp-preview` (that endpoint exists for QA's convenience, not as a
substitute for you verifying the actual webhook path).

## Explicitly not your job

Report computation, message text formatting/rendering, fuzzy match scoring (all Business Logic — you call
into it and handle only the intent-routing and Twilio-shaped request/response).
