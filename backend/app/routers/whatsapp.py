"""backend/app/routers/whatsapp.py — Twilio WhatsApp webhook (API_SPEC.md §9).

Turns an inbound WhatsApp message into a routed call to Business Logic's
report functions and sends the rendered text back as inline TwiML.

Scope (FOLDER_STRUCTURE.md §Rules):
- This file is the only file the WhatsApp agent touches inside backend/.
- All ageing, fuzzy-matching, and message-formatting logic lives in
  business_logic/; this module only handles intent-routing and
  Twilio-shaped request/response.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any
from xml.sax.saxutils import escape

from fastapi import APIRouter, Form
from fastapi.responses import Response

from ..business_logic.ageing import (
    CustomerNotFoundError as BLCustomerNotFoundError,
    get_today,
    InvoiceRecord,
)
from ..business_logic.matching import CustomerRef, resolve_customer_name
from ..business_logic.render import (
    render_collection_followup_message,
    render_payment_schedule_message,
)
from ..business_logic.reports import get_collection_followup, get_payment_schedule
from ..storage.store import store_instance
from datetime import date

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Intent keywords (AGENT_PROMPT_WHATSAPP.md §Intent parsing)
# ---------------------------------------------------------------------------

_COLLECTION_KEYWORDS: frozenset[str] = frozenset({"collection", "follow-up", "followup"})
_SCHEDULE_KEYWORDS: frozenset[str] = frozenset({"payment", "schedule"})

# Filler words stripped before extracting the customer-name candidate.
_FILLER_WORDS: frozenset[str] = frozenset(
    {"give", "me", "a", "weekly", "for", "the", "get", "please", "send"}
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _twiml_reply(message: str) -> Response:
    """Construct a TwiML Response wrapping *message*.

    XML-escapes the text so customer names or currency symbols containing
    ``&``, ``<``, or ``>`` do not break the XML envelope (AGENT_PROMPT).
    """
    xml = (
        "<?xml version='1.0' encoding='UTF-8'?>"
        f"<Response><Message>{escape(message)}</Message></Response>"
    )
    return Response(content=xml, media_type="text/xml")


def _parse_intent(body_lower: str) -> str | None:
    """Return ``'payment_schedule'``, ``'collection_followup'``, or ``None``.

    Implements the keyword-precedence rule from AGENT_PROMPT_WHATSAPP.md:
    - ``collection`` / ``follow-up`` / ``followup`` → collection_followup
    - ``payment`` / ``schedule`` (and NOT the collection keywords) → payment_schedule
    - Both keyword sets present, or neither → None (ask for clarification)
    """
    has_collection = any(kw in body_lower for kw in _COLLECTION_KEYWORDS)
    has_schedule = any(kw in body_lower for kw in _SCHEDULE_KEYWORDS)

    if has_collection and not has_schedule:
        return "collection_followup"
    if has_schedule and not has_collection:
        return "payment_schedule"
    # Both or neither — ambiguous.
    return None


def _extract_customer_name(body_lower: str) -> str:
    """Strip intent keywords and filler words; return the remainder.

    This is intentionally simple — the fuzzy matcher in Business Logic
    absorbs imprecision. An empty string is returned when nothing useful
    remains (caller must handle this).
    """
    remove_tokens = (
        _COLLECTION_KEYWORDS
        | _SCHEDULE_KEYWORDS
        | _FILLER_WORDS
    )
    tokens = body_lower.split()
    candidate_tokens = [t for t in tokens if t not in remove_tokens]
    return " ".join(candidate_tokens).strip()


def _get_customer_refs() -> list[CustomerRef]:
    """Build a list of CustomerRef objects from the in-memory store.

    Mirrors the pattern in customers.py::resolve_customer without importing
    from that module (routers must not import from sibling routers).
    """
    raw_invoices: list[dict[str, Any]] = store_instance.get_invoices()
    seen: dict[str, str] = {}  # customer_key → display_name (first occurrence wins as tiebreak)
    for inv in raw_invoices:
        key: str = inv["customer_key"]
        if key not in seen:
            seen[key] = inv["customer_raw"]
    return [CustomerRef(customer_key=k, display_name=v) for k, v in seen.items()]


def _raw_to_invoice_record(raw: dict[str, Any]) -> InvoiceRecord:
    """Convert a stored invoice dict into an InvoiceRecord for business logic.

    Identical conversion logic to customers.py — kept here to avoid
    cross-router imports (FOLDER_STRUCTURE.md §Rules).
    """
    due_date_str: str | None = raw.get("due_date")
    inv_date_str: str | None = raw.get("invoice_date")
    return InvoiceRecord(
        id=raw["id"],
        customer_raw=raw["customer_raw"],
        customer_key=raw["customer_key"],
        spoc=raw.get("spoc"),
        invoice_no=raw["invoice_no"],
        invoice_date=date.fromisoformat(inv_date_str) if inv_date_str else None,
        due_date=date.fromisoformat(due_date_str) if due_date_str else None,
        inv_amount=raw["inv_amount"],
        received=raw["received"],
        outstanding=raw["outstanding"],
    )


# ---------------------------------------------------------------------------
# POST /api/whatsapp/webhook   (API_SPEC.md §9)
# ---------------------------------------------------------------------------

_HELP_MESSAGE: str = (
    "Hi! I can help with two types of reports:\n\n"
    "1. *Payment Schedule* — e.g., \"payment schedule for ABC\"\n"
    "2. *Collection Follow-up* — e.g., \"collection followup for XYZ\"\n\n"
    "Please include the customer name in your message."
)

_NO_CUSTOMER_MESSAGE: str = (
    "Please include a customer name in your message.\n\n"
    "Example: \"payment schedule for ABC Pvt Ltd\""
)


@router.post("/webhook")
async def whatsapp_webhook(
    Body: Annotated[str, Form()] = "",
    From: Annotated[str, Form()] = "",
) -> Response:
    """Handle an inbound Twilio WhatsApp message.

    Always returns HTTP 200 with a TwiML ``<Response><Message>`` envelope.
    Never returns a raw 4xx/5xx to Twilio — non-2xx causes Twilio to retry
    and alert, which is the wrong behavior for user-facing errors such as
    "customer not found" (API_SPEC.md §9).

    Flow:
    1. Parse intent from lowercased ``Body`` (keyword matching).
    2. Extract candidate customer name by stripping known tokens.
    3. Fuzzy-resolve customer via ``business_logic.matching``.
    4. Generate the report via ``business_logic.reports``.
    5. Render the message via ``business_logic.render``.
    6. Return TwiML with the rendered text.
    """
    sender: str = From or "unknown"
    logger.info("Inbound WhatsApp message from %s: %r", sender, Body)

    try:
        reply_text = _process_message(Body)
    except Exception:
        logger.exception(
            "Unexpected error processing WhatsApp message from %s: %r",
            sender,
            Body,
        )
        reply_text = (
            "Sorry, something went wrong on our end. "
            "Please try again in a moment."
        )

    return _twiml_reply(reply_text)


def _process_message(body: str) -> str:
    """Core message-processing logic extracted for testability.

    Returns the plain-text reply string (not yet TwiML-wrapped).
    All branches must return a string — never raise (caller wraps in try/except).
    """
    body_lower = body.lower().strip()

    # ------------------------------------------------------------------
    # Step 1: Determine intent
    # ------------------------------------------------------------------
    intent = _parse_intent(body_lower)

    if intent is None:
        logger.info("No recognizable intent in message: %r", body)
        return _HELP_MESSAGE

    # ------------------------------------------------------------------
    # Step 2: Extract candidate customer name
    # ------------------------------------------------------------------
    candidate_name = _extract_customer_name(body_lower)

    if not candidate_name:
        logger.info("Intent '%s' recognised but no customer name found in: %r", intent, body)
        return _NO_CUSTOMER_MESSAGE

    # ------------------------------------------------------------------
    # Step 3: Check data availability
    # ------------------------------------------------------------------
    raw_invoices: list[dict[str, Any]] = store_instance.get_invoices()

    if not raw_invoices:
        return (
            "No invoice data is loaded yet. "
            "Please ask your administrator to upload the AR sheet first."
        )

    # ------------------------------------------------------------------
    # Step 4: Fuzzy-resolve customer name
    # ------------------------------------------------------------------
    customer_refs = _get_customer_refs()
    match_result = resolve_customer_name(candidate_name, customer_refs)

    if not match_result.matched:
        candidates_text = _format_candidates(match_result.candidates)
        logger.info(
            "Customer not resolved for query %r (candidates: %s)",
            candidate_name,
            candidates_text,
        )
        reply = f"Couldn't find a customer matching \"{candidate_name}\"."
        if match_result.candidates:
            reply += f"\n\nDid you mean:\n{candidates_text}"
        return reply

    customer_key: str = match_result.customer_key  # type: ignore[assignment]
    logger.info(
        "Resolved %r → customer_key=%r (confidence=%.1f)",
        candidate_name,
        customer_key,
        match_result.confidence,
    )

    # ------------------------------------------------------------------
    # Step 5: Generate report data
    # ------------------------------------------------------------------
    today = get_today()
    invoice_records = [_raw_to_invoice_record(r) for r in raw_invoices]

    try:
        if intent == "payment_schedule":
            schedule = get_payment_schedule(customer_key, invoice_records, today)
            return render_payment_schedule_message(schedule)
        else:  # collection_followup
            followup = get_collection_followup(customer_key, invoice_records, today)
            return render_collection_followup_message(followup)
    except BLCustomerNotFoundError:
        # Resolved by fuzzy match but no invoices for that key — shouldn't
        # happen in normal operation, but handle gracefully.
        logger.warning(
            "Fuzzy match resolved to %r but no invoices found in store.", customer_key
        )
        return (
            f"Found a match for \"{match_result.display_name}\", "
            "but no invoice data is available for them. "
            "Please contact your administrator."
        )


def _format_candidates(candidates: list[CustomerRef]) -> str:
    """Format a list of CustomerRef objects as a bulleted plain-text list."""
    return "\n".join(f"• {c.display_name}" for c in candidates)
