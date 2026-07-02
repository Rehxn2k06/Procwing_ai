"""backend/app/errors.py — ErrorResponse model, AppError hierarchy, exception handlers."""

from __future__ import annotations

import logging

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Error code constants (CODING_STANDARDS.md §3)
# ---------------------------------------------------------------------------
ERROR_CODE_INVALID_FILE_TYPE: str = "INVALID_FILE_TYPE"
ERROR_CODE_MISSING_COLUMNS: str = "MISSING_COLUMNS"
ERROR_CODE_PARSE_ERROR: str = "PARSE_ERROR"
ERROR_CODE_CUSTOMER_NOT_FOUND: str = "CUSTOMER_NOT_FOUND"
ERROR_CODE_NO_DATA_UPLOADED: str = "NO_DATA_UPLOADED"
ERROR_CODE_VALIDATION_ERROR: str = "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# Standard error response shape (API_SPEC.md §0)
# ---------------------------------------------------------------------------
class ErrorResponse(BaseModel):
    """Standard JSON error envelope returned by every non-2xx response."""

    error: str = Field(..., description="Machine-readable error code.")
    message: str = Field(..., description="Human-readable error description.")


# ---------------------------------------------------------------------------
# Application exception hierarchy
# ---------------------------------------------------------------------------
class AppError(Exception):
    """Base class for all application-level HTTP errors.

    Raise an AppError subclass (or AppError directly) from a router; the
    registered exception handler converts it to an ErrorResponse JSONResponse.
    """

    def __init__(self, error_code: str, message: str, status_code: int = 400) -> None:
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        super().__init__(f"[{error_code}] {message}")


class CustomerNotFoundError(AppError):
    """Raised when a customer_key has no invoices in the store."""

    def __init__(self, customer_key: str) -> None:
        super().__init__(
            error_code=ERROR_CODE_CUSTOMER_NOT_FOUND,
            message=f"Customer '{customer_key}' not found.",
            status_code=404,
        )


class NoDataUploadedError(AppError):
    """Raised when a read endpoint is called before any upload has occurred."""

    def __init__(self) -> None:
        super().__init__(
            error_code=ERROR_CODE_NO_DATA_UPLOADED,
            message="No data uploaded yet. Please POST to /api/upload first.",
            status_code=409,
        )


# ---------------------------------------------------------------------------
# FastAPI exception handlers
# ---------------------------------------------------------------------------
async def app_error_exception_handler(request: Request, exc: AppError) -> JSONResponse:
    """Convert AppError (and subclasses) into the standard ErrorResponse shape."""
    logger.warning("AppError %s: %s", exc.error_code, exc.message)
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(error=exc.error_code, message=exc.message).model_dump(),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Wrap FastAPI's RequestValidationError (422) into ErrorResponse shape."""
    detail = "; ".join(
        f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}"
        for e in exc.errors()
    )
    logger.warning("Validation error on %s: %s", request.url, detail)
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            error=ERROR_CODE_VALIDATION_ERROR,
            message=detail,
        ).model_dump(),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Wrap FastAPI's HTTPException into ErrorResponse shape."""
    logger.warning("HTTPException %d on %s: %s", exc.status_code, request.url, exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error="HTTP_ERROR",
            message=str(exc.detail),
        ).model_dump(),
    )
