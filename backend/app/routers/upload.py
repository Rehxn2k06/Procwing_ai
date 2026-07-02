"""backend/app/routers/upload.py — POST /api/upload."""

from __future__ import annotations

import asyncio
import io
import logging
import uuid
from datetime import datetime
from typing import Any

import pandas as pd
from fastapi import APIRouter, File, UploadFile

from ..business_logic.customer_key import normalize
from ..config import IST
from ..errors import (
    AppError,
    ERROR_CODE_INVALID_FILE_TYPE,
    ERROR_CODE_MISSING_COLUMNS,
    ERROR_CODE_PARSE_ERROR,
)
from ..models.schemas import UploadResponse, UploadWarning
from ..storage.store import FileSaveError, store_instance

logger = logging.getLogger(__name__)

router = APIRouter()

# Required column headers exactly as specified in DATABASE_SCHEMA.md §6.
REQUIRED_COLUMNS: list[str] = [
    "Customer",
    "SPOC",
    "Invoice No",
    "Invoice Date",
    "Due Date",
    "Inv Amount",
    "Received",
    "Outstanding",
]


# ---------------------------------------------------------------------------
# Parsing helper (synchronous — called via asyncio.to_thread)
# ---------------------------------------------------------------------------


def _parse_excel(
    content: bytes, filename: str
) -> tuple[list[dict[str, Any]], list[UploadWarning]]:
    """Parse the xlsx bytes and return (invoice_records, warnings).

    Raises AppError on invalid file type, missing columns, or parse failure.
    Does NOT raise on a missing Due Date — that is a warning, not an error.
    """
    if not filename.lower().endswith(".xlsx"):
        raise AppError(
            error_code=ERROR_CODE_INVALID_FILE_TYPE,
            message="Uploaded file must be an .xlsx spreadsheet.",
            status_code=400,
        )

    try:
        df = pd.read_excel(io.BytesIO(content), engine="openpyxl")
    except Exception as exc:
        raise AppError(
            error_code=ERROR_CODE_PARSE_ERROR,
            message=f"Could not read the Excel file: {exc}",
            status_code=400,
        ) from exc

    # Trim whitespace from column headers (DATABASE_SCHEMA.md §6).
    df.columns = [str(c).strip() for c in df.columns]

    # Validate required columns — exact match, no fuzzy guessing.
    actual_lower = {c.lower() for c in df.columns}
    required_lower = {c.lower() for c in REQUIRED_COLUMNS}
    missing = required_lower - actual_lower
    if missing:
        raise AppError(
            error_code=ERROR_CODE_MISSING_COLUMNS,
            message=(
                f"Missing required columns: {', '.join(sorted(missing))}. "
                f"Found: {', '.join(df.columns)}."
            ),
            status_code=400,
        )

    # Build a case-insensitive column-name lookup.
    col_map: dict[str, str] = {c.lower(): c for c in df.columns}

    invoices: list[dict[str, Any]] = []
    warnings: list[UploadWarning] = []

    for idx, row in df.iterrows():
        row_num = int(idx) + 2  # 1-indexed + header row

        # ------------------------------------------------------------------
        # Extract fields
        # ------------------------------------------------------------------
        customer_raw = str(row[col_map["customer"]]).strip()
        customer_key = normalize(customer_raw)

        spoc_val = row[col_map["spoc"]]
        spoc: str | None = (
            str(spoc_val).strip() if pd.notna(spoc_val) and str(spoc_val).strip() else None
        )

        invoice_no = str(row[col_map["invoice no"]]).strip()

        # -- Invoice Date --
        inv_date_val = row[col_map["invoice date"]]
        if pd.isna(inv_date_val):
            invoice_date: str | None = None
        elif isinstance(inv_date_val, pd.Timestamp):
            invoice_date = inv_date_val.date().isoformat()
        else:
            try:
                invoice_date = pd.Timestamp(inv_date_val).date().isoformat()
            except Exception:
                invoice_date = None

        # -- Due Date (missing due date is a warning, not an error) --
        due_date_val = row[col_map["due date"]]
        if pd.isna(due_date_val):
            due_date: str | None = None
            warnings.append(
                UploadWarning(row=row_num, invoice_no=invoice_no, issue="missing_due_date")
            )
        elif isinstance(due_date_val, pd.Timestamp):
            due_date = due_date_val.date().isoformat()
        else:
            try:
                due_date = pd.Timestamp(due_date_val).date().isoformat()
            except Exception:
                due_date = None
                warnings.append(
                    UploadWarning(
                        row=row_num, invoice_no=invoice_no, issue="unparseable_due_date"
                    )
                )

        # -- Monetary amounts --
        try:
            inv_amount = float(row[col_map["inv amount"]])
            received = float(row[col_map["received"]])
            outstanding = float(row[col_map["outstanding"]])
        except (ValueError, TypeError) as exc:
            raise AppError(
                error_code=ERROR_CODE_PARSE_ERROR,
                message=f"Row {row_num} ({invoice_no}): numeric conversion failed — {exc}.",
                status_code=400,
            ) from exc

        invoices.append(
            {
                "id": str(uuid.uuid4()),
                "customer_raw": customer_raw,
                "customer_key": customer_key,
                "spoc": spoc,
                "invoice_no": invoice_no,
                "invoice_date": invoice_date,
                "due_date": due_date,
                "inv_amount": inv_amount,
                "received": received,
                "outstanding": outstanding,
            }
        )

    return invoices, warnings


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("", response_model=UploadResponse)
async def upload_excel(file: UploadFile = File(...)) -> UploadResponse:
    """Upload an AR sheet (.xlsx).  Replaces the entire data store on success."""
    content: bytes = await file.read()

    # Run synchronous pandas parsing off the event loop thread.
    invoices, warnings = await asyncio.to_thread(
        _parse_excel, content, file.filename or ""
    )

    uploaded_at = datetime.now(IST).isoformat()

    try:
        store_instance.save_invoices(
            invoices,
            uploaded_at=uploaded_at,
            source_filename=file.filename,
        )
    except FileSaveError as exc:
        raise AppError(
            error_code=ERROR_CODE_PARSE_ERROR,
            message=f"Data was parsed but could not be saved: {exc}",
            status_code=500,
        ) from exc

    total_outstanding = sum(inv["outstanding"] for inv in invoices)
    customers_count = len({inv["customer_key"] for inv in invoices})
    invoices_count = len(invoices)

    logger.info(
        "Upload complete: %d invoices, %d customers, %d warnings.",
        invoices_count,
        customers_count,
        len(warnings),
    )

    return UploadResponse(
        customers_count=customers_count,
        invoices_count=invoices_count,
        total_outstanding=total_outstanding,
        warnings=warnings,
    )
