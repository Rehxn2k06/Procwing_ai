"""backend/app/routers/customers.py — Customer list, resolve, schedules, preview."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import date
from typing import Any

from fastapi import APIRouter, Query

from ..business_logic.ageing import (
    CustomerNotFoundError as BLCustomerNotFoundError,
    get_today,
)
from ..business_logic.matching import CustomerRef, resolve_customer_name
from ..business_logic.render import (
    render_collection_followup_message,
    render_payment_schedule_message,
)
from ..business_logic.reports import get_collection_followup, get_payment_schedule
from ..business_logic.ageing import InvoiceRecord
from ..errors import AppError, CustomerNotFoundError, ERROR_CODE_NO_DATA_UPLOADED
from ..models.schemas import (
    CandidateMatch,
    CollectionFollowupResponse,
    CustomerInfo,
    CustomerListResponse,
    CustomerResolveResponse,
    DailyBreakdownEntry,
    PaymentScheduleInvoice,
    PaymentScheduleResponse,
    WhatsappPreviewResponse,
)
from ..storage.store import store_instance

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _require_data() -> list[dict[str, Any]]:
    """Return stored invoices or raise NO_DATA_UPLOADED."""
    invoices = store_instance.get_invoices()
    if not invoices:
        raise AppError(
            error_code=ERROR_CODE_NO_DATA_UPLOADED,
            message="No invoice data available. Upload a sheet via POST /api/upload first.",
            status_code=409,
        )
    return invoices


def _build_customer_map(
    raw_invoices: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Aggregate per-customer metadata from the raw invoice list.

    Returns a dict keyed by customer_key with:
      display_name  — most-frequent customer_raw (first-occurrence tie-break)
      spoc          — SPOC from the most-recent invoice by invoice_date
    """
    # {customer_key: Counter({raw_name: count})}
    name_counters: dict[str, Counter] = {}
    # {customer_key: (latest_date_str, spoc)}
    spoc_tracker: dict[str, tuple[str, str | None]] = {}

    for inv in raw_invoices:
        key: str = inv["customer_key"]
        raw_name: str = inv["customer_raw"]
        spoc: str | None = inv.get("spoc")
        inv_date_str: str | None = inv.get("invoice_date")

        # Track raw name frequency (Counter preserves insertion order for ties).
        if key not in name_counters:
            name_counters[key] = Counter()
        name_counters[key][raw_name] += 1

        # Track SPOC from the most-recent invoice.
        prev_date, _ = spoc_tracker.get(key, ("", None))
        if spoc and (inv_date_str or "") > prev_date:
            spoc_tracker[key] = (inv_date_str or "", spoc)

    result: dict[str, dict[str, Any]] = {}
    for key, counter in name_counters.items():
        # most_common()[0] returns (name, count); tie-break by first occurrence
        # because Counter preserves insertion order in CPython 3.7+.
        display_name = counter.most_common(1)[0][0]
        _, spoc_val = spoc_tracker.get(key, ("", None))
        result[key] = {"display_name": display_name, "spoc": spoc_val}

    return result


def _raw_to_invoice_record(raw: dict[str, Any]) -> InvoiceRecord:
    """Convert a stored dict into an InvoiceRecord dataclass for business logic."""
    due_date_str = raw.get("due_date")
    inv_date_str = raw.get("invoice_date")
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
# GET /api/customers
# ---------------------------------------------------------------------------


@router.get("", response_model=CustomerListResponse)
async def get_customers() -> CustomerListResponse:
    """List all distinct customers with display name and SPOC."""
    raw_invoices = _require_data()
    cmap = _build_customer_map(raw_invoices)

    customers = sorted(
        [
            CustomerInfo(
                customer_key=key,
                display_name=data["display_name"],
                spoc=data["spoc"],
            )
            for key, data in cmap.items()
        ],
        key=lambda c: c.display_name.lower(),
    )
    return CustomerListResponse(customers=customers)


# ---------------------------------------------------------------------------
# GET /api/customers/resolve
# ---------------------------------------------------------------------------


@router.get("/resolve", response_model=CustomerResolveResponse)
async def resolve_customer(
    query: str = Query(..., description="Free-text customer name to fuzzy-resolve."),
) -> CustomerResolveResponse:
    """Fuzzy-resolve a free-text query to a customer_key."""
    raw_invoices = _require_data()
    cmap = _build_customer_map(raw_invoices)

    customer_refs = [
        CustomerRef(customer_key=key, display_name=data["display_name"])
        for key, data in cmap.items()
    ]

    result = resolve_customer_name(query, customer_refs)

    # MatchResult.candidates is a list[CustomerRef]; we need confidence per candidate.
    # resolve_customer_name returns scored_candidates internally but exposes only the
    # top CustomerRef objects.  We call it again with the knowledge that candidates'
    # scores are not returned — expose confidence=0 for non-top candidates as per spec
    # (the spec only guarantees confidence on the top match).
    candidates = [
        CandidateMatch(
            customer_key=c.customer_key,
            display_name=c.display_name,
            confidence=result.confidence if c.customer_key == result.customer_key else 0.0,
        )
        for c in result.candidates
    ]

    return CustomerResolveResponse(
        matched=result.matched,
        customer_key=result.customer_key,
        display_name=result.display_name,
        confidence=result.confidence,
        candidates=candidates,
    )


# ---------------------------------------------------------------------------
# GET /api/customers/{customer_key}/payment-schedule
# ---------------------------------------------------------------------------


@router.get("/{customer_key}/payment-schedule", response_model=PaymentScheduleResponse)
async def get_payment_schedule_endpoint(customer_key: str) -> PaymentScheduleResponse:
    """Return structured payment-schedule data for a customer."""
    raw_invoices = _require_data()
    today = get_today()
    invoice_records = [_raw_to_invoice_record(r) for r in raw_invoices]

    try:
        schedule = get_payment_schedule(customer_key, invoice_records, today)
    except BLCustomerNotFoundError:
        raise CustomerNotFoundError(customer_key)

    return PaymentScheduleResponse(
        customer_key=schedule.customer_key,
        display_name=schedule.display_name,
        spoc=schedule.spoc,
        overdue_amount=schedule.overdue_amount,
        due_this_week=schedule.due_this_week,
        total_outstanding=schedule.total_outstanding,
        ageing_breakdown=schedule.ageing_breakdown,
        invoices=[
            PaymentScheduleInvoice(
                invoice_no=inv["invoice_no"],
                due_date=inv.get("due_date"),
                outstanding=inv["outstanding"],
            )
            for inv in schedule.invoices
        ],
        no_due_date_count=schedule.no_due_date_count,
        no_due_date_total=schedule.no_due_date_total,
    )


# ---------------------------------------------------------------------------
# GET /api/customers/{customer_key}/collection-followup
# ---------------------------------------------------------------------------


@router.get("/{customer_key}/collection-followup", response_model=CollectionFollowupResponse)
async def get_collection_followup_endpoint(customer_key: str) -> CollectionFollowupResponse:
    """Return structured collection-followup data for a customer."""
    raw_invoices = _require_data()
    today = get_today()
    invoice_records = [_raw_to_invoice_record(r) for r in raw_invoices]

    try:
        followup = get_collection_followup(customer_key, invoice_records, today)
    except BLCustomerNotFoundError:
        raise CustomerNotFoundError(customer_key)

    return CollectionFollowupResponse(
        customer_key=followup.customer_key,
        display_name=followup.display_name,
        spoc=followup.spoc,
        overdue_amount=followup.overdue_amount,
        due_this_week=followup.due_this_week,
        week_start=followup.week_start.isoformat(),
        week_end=followup.week_end.isoformat(),
        total_collection_target=followup.total_collection_target,
        daily_breakdown=[
            DailyBreakdownEntry(
                label=entry["label"],
                date=entry.get("date"),
                amount=entry["amount"],
            )
            for entry in followup.daily_breakdown
        ],
        invoices=[
            PaymentScheduleInvoice(
                invoice_no=inv["invoice_no"],
                due_date=inv.get("due_date"),
                outstanding=inv["outstanding"],
            )
            for inv in followup.invoices
        ],
    )


# ---------------------------------------------------------------------------
# GET /api/customers/{customer_key}/whatsapp-preview
# ---------------------------------------------------------------------------

_VALID_REPORT_TYPES: set[str] = {"payment_schedule", "collection_followup"}


@router.get("/{customer_key}/whatsapp-preview", response_model=WhatsappPreviewResponse)
async def get_whatsapp_preview(
    customer_key: str,
    type: str = Query(
        ...,
        description="Report type: payment_schedule | collection_followup",
    ),
) -> WhatsappPreviewResponse:
    """Return the exact rendered WhatsApp message for a customer report.

    Uses the same Business Logic render functions as the WhatsApp webhook,
    ensuring the two paths can never drift apart.
    """
    if type not in _VALID_REPORT_TYPES:
        raise AppError(
            error_code="INVALID_REPORT_TYPE",
            message=f"type must be one of: {', '.join(sorted(_VALID_REPORT_TYPES))}.",
            status_code=400,
        )

    raw_invoices = _require_data()
    today = get_today()
    invoice_records = [_raw_to_invoice_record(r) for r in raw_invoices]

    try:
        if type == "payment_schedule":
            schedule = get_payment_schedule(customer_key, invoice_records, today)
            message = render_payment_schedule_message(schedule)
        else:  # collection_followup
            followup = get_collection_followup(customer_key, invoice_records, today)
            message = render_collection_followup_message(followup)
    except BLCustomerNotFoundError:
        raise CustomerNotFoundError(customer_key)

    return WhatsappPreviewResponse(message=message)
