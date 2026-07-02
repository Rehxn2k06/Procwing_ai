"""backend/app/routers/invoices.py — GET /api/invoices/summary and GET /api/invoices."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, Query

from ..business_logic.ageing import (
    compute_ageing_bucket,
    compute_days_overdue,
    compute_is_due_this_week,
    get_current_week,
    get_today,
)
from ..errors import AppError, ERROR_CODE_NO_DATA_UPLOADED
from ..models.schemas import (
    AgeingBucketSummary,
    Invoice,
    InvoiceListResponse,
    InvoiceSummaryResponse,
)
from ..storage.store import store_instance

logger = logging.getLogger(__name__)

router = APIRouter()

# Ordered bucket list for the summary response (API_SPEC.md §2).
_BUCKET_ORDER: list[str] = [
    "ALL",
    "NOT_DUE",
    "0-15",
    "16-30",
    "31-60",
    "61-90",
    "90+",
    "NO_DUE_DATE",
]


# ---------------------------------------------------------------------------
# Helper — compute all ageing fields for a stored invoice dict
# ---------------------------------------------------------------------------


def _enrich_invoice(raw: dict[str, Any], today: date, week_start: date, week_end: date) -> Invoice:
    """Attach computed ageing fields to a raw stored invoice dict and return Invoice."""
    due_date_str: str | None = raw.get("due_date")
    due_date: date | None = date.fromisoformat(due_date_str) if due_date_str else None

    bucket = compute_ageing_bucket(due_date, today)
    days_overdue = compute_days_overdue(due_date, today)
    is_due_this_week = compute_is_due_this_week(due_date, week_start, week_end)

    return Invoice(
        id=raw["id"],
        customer_raw=raw["customer_raw"],
        customer_key=raw["customer_key"],
        spoc=raw.get("spoc"),
        invoice_no=raw["invoice_no"],
        invoice_date=raw.get("invoice_date"),
        due_date=due_date_str,
        inv_amount=raw["inv_amount"],
        received=raw["received"],
        outstanding=raw["outstanding"],
        ageing_bucket=bucket,
        days_overdue=days_overdue,
        is_due_this_week=is_due_this_week,
    )


def _require_data() -> list[dict[str, Any]]:
    """Return invoices from the store or raise NO_DATA_UPLOADED (409)."""
    invoices = store_instance.get_invoices()
    if not invoices:
        raise AppError(
            error_code=ERROR_CODE_NO_DATA_UPLOADED,
            message="No invoice data available. Upload a sheet via POST /api/upload first.",
            status_code=409,
        )
    return invoices


# ---------------------------------------------------------------------------
# GET /api/invoices/summary
# ---------------------------------------------------------------------------


@router.get("/summary", response_model=InvoiceSummaryResponse)
async def get_invoice_summary() -> InvoiceSummaryResponse:
    """Bucket-level counts and totals.  Powers the tab row on the frontend."""
    raw_invoices = _require_data()
    today = get_today()
    week_start, week_end = get_current_week(today)

    counts: dict[str, int] = {b: 0 for b in _BUCKET_ORDER}
    totals: dict[str, float] = {b: 0.0 for b in _BUCKET_ORDER}

    for raw in raw_invoices:
        due_date_str: str | None = raw.get("due_date")
        due_date = date.fromisoformat(due_date_str) if due_date_str else None
        bucket = compute_ageing_bucket(due_date, today)
        outstanding = float(raw.get("outstanding", 0.0))

        counts["ALL"] += 1
        totals["ALL"] += outstanding
        counts[bucket] += 1
        totals[bucket] += outstanding

    buckets: list[AgeingBucketSummary] = []
    for b in _BUCKET_ORDER:
        # Only include NO_DUE_DATE if count > 0 is handled by Frontend; we always
        # return all buckets so the frontend can decide what to show.
        buckets.append(
            AgeingBucketSummary(bucket=b, count=counts[b], total_outstanding=totals[b])
        )

    return InvoiceSummaryResponse(buckets=buckets)


# ---------------------------------------------------------------------------
# GET /api/invoices
# ---------------------------------------------------------------------------


@router.get("", response_model=InvoiceListResponse)
async def get_invoices(
    bucket: str = Query(
        "ALL",
        description="Filter by ageing bucket (ALL | NOT_DUE | 0-15 | 16-30 | 31-60 | 61-90 | 90+ | NO_DUE_DATE)",
    ),
    search: str | None = Query(
        None,
        description="Case-insensitive substring match against customer_raw or invoice_no.",
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)."),
    page_size: int = Query(50, ge=1, le=200, description="Items per page (max 200)."),
) -> InvoiceListResponse:
    """Filtered, paginated invoice list.  Powers the table under the bucket tabs."""
    raw_invoices = _require_data()
    today = get_today()
    week_start, week_end = get_current_week(today)

    # Enrich all invoices with computed fields (ageing is computed at read time —
    # DATABASE_SCHEMA.md §1: computed fields are never stored).
    enriched: list[Invoice] = [
        _enrich_invoice(raw, today, week_start, week_end) for raw in raw_invoices
    ]

    # -- Bucket filter --
    if bucket != "ALL":
        enriched = [inv for inv in enriched if inv.ageing_bucket == bucket]

    # -- Search filter (customer_raw OR invoice_no, case-insensitive substring) --
    if search:
        q = search.lower()
        enriched = [
            inv
            for inv in enriched
            if q in inv.customer_raw.lower() or q in inv.invoice_no.lower()
        ]

    total_count = len(enriched)
    start = (page - 1) * page_size
    page_items = enriched[start : start + page_size]

    return InvoiceListResponse(
        items=page_items,
        total_count=total_count,
        page=page,
        page_size=page_size,
    )
