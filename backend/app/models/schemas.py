"""backend/app/models/schemas.py — All Pydantic models, literal translation of API_SPEC.md."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# §0  Shared types
# ---------------------------------------------------------------------------

class Invoice(BaseModel):
    """Full invoice row including computed ageing fields.

    Pydantic serialises with snake_case keys by default, matching the
    API_SPEC.md §0 backend JSON contract.  The frontend API client is
    responsible for the one-time snake_case → camelCase conversion.
    """

    id: str  # uuid4 string, stable for the life of the upload
    customer_raw: str
    customer_key: str
    spoc: str | None = None
    invoice_no: str
    invoice_date: str | None = None  # "YYYY-MM-DD" or null
    due_date: str | None = None  # "YYYY-MM-DD" or null
    inv_amount: float
    received: float
    outstanding: float
    ageing_bucket: str  # NOT_DUE | 0-15 | 16-30 | 31-60 | 61-90 | 90+ | NO_DUE_DATE
    days_overdue: int | None = None
    is_due_this_week: bool


class ErrorResponse(BaseModel):
    """Standard error envelope — API_SPEC.md §0."""

    error: str
    message: str


# ---------------------------------------------------------------------------
# §1  POST /api/upload
# ---------------------------------------------------------------------------

class UploadWarning(BaseModel):
    """Single warning entry produced during sheet parsing."""

    row: int
    invoice_no: str
    issue: str


class UploadResponse(BaseModel):
    """Response for POST /api/upload."""

    customers_count: int
    invoices_count: int
    total_outstanding: float
    warnings: list[UploadWarning]


# ---------------------------------------------------------------------------
# §2  GET /api/invoices/summary
# ---------------------------------------------------------------------------

class AgeingBucketSummary(BaseModel):
    """Count + total outstanding for one ageing bucket or ALL."""

    bucket: str
    count: int
    total_outstanding: float


class InvoiceSummaryResponse(BaseModel):
    """Response for GET /api/invoices/summary."""

    buckets: list[AgeingBucketSummary]


# ---------------------------------------------------------------------------
# §3  GET /api/invoices
# ---------------------------------------------------------------------------

class InvoiceListResponse(BaseModel):
    """Paginated invoice list response."""

    items: list[Invoice]
    total_count: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# §4  GET /api/customers
# ---------------------------------------------------------------------------

class CustomerInfo(BaseModel):
    """Distinct customer entry for dropdown/lookup responses."""

    customer_key: str
    display_name: str
    spoc: str | None = None


class CustomerListResponse(BaseModel):
    """Response for GET /api/customers."""

    customers: list[CustomerInfo]


# ---------------------------------------------------------------------------
# §5  GET /api/customers/resolve
# ---------------------------------------------------------------------------

class CandidateMatch(BaseModel):
    """One fuzzy-match candidate returned by /resolve."""

    customer_key: str
    display_name: str
    confidence: float


class CustomerResolveResponse(BaseModel):
    """Response for GET /api/customers/resolve."""

    matched: bool
    customer_key: str | None = None
    display_name: str | None = None
    confidence: float = 0.0
    candidates: list[CandidateMatch]


# ---------------------------------------------------------------------------
# §6  GET /api/customers/{customer_key}/payment-schedule
# ---------------------------------------------------------------------------

class PaymentScheduleInvoice(BaseModel):
    """Minimal invoice summary inside a payment-schedule response."""

    invoice_no: str
    due_date: str | None = None
    outstanding: float


class PaymentScheduleResponse(BaseModel):
    """Response for GET /api/customers/{customer_key}/payment-schedule."""

    customer_key: str
    display_name: str
    spoc: str | None = None
    overdue_amount: float
    due_this_week: float
    total_outstanding: float
    ageing_breakdown: dict[str, float]
    invoices: list[PaymentScheduleInvoice]
    no_due_date_count: int
    no_due_date_total: float


# ---------------------------------------------------------------------------
# §7  GET /api/customers/{customer_key}/collection-followup
# ---------------------------------------------------------------------------

class DailyBreakdownEntry(BaseModel):
    """One row of the daily collection breakdown."""

    label: str
    date: str | None = None  # ISO date string or null
    amount: float


class CollectionFollowupResponse(BaseModel):
    """Response for GET /api/customers/{customer_key}/collection-followup."""

    customer_key: str
    display_name: str
    spoc: str | None = None
    overdue_amount: float
    due_this_week: float
    week_start: str  # ISO date string
    week_end: str  # ISO date string
    total_collection_target: float
    daily_breakdown: list[DailyBreakdownEntry]
    invoices: list[PaymentScheduleInvoice]  # same minimal shape as payment-schedule


# ---------------------------------------------------------------------------
# §8  GET /api/customers/{customer_key}/whatsapp-preview
# ---------------------------------------------------------------------------

class WhatsappPreviewResponse(BaseModel):
    """Response for GET /api/customers/{customer_key}/whatsapp-preview."""

    message: str


# ---------------------------------------------------------------------------
# §10  GET /api/health
# ---------------------------------------------------------------------------

class HealthCheckResponse(BaseModel):
    """Response for GET /api/health."""

    status: str
    invoices_loaded: int
