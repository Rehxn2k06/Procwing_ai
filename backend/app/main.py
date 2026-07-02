"""backend/app/main.py — FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .errors import (
    AppError,
    app_error_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from .routers import customers, health, invoices, upload, whatsapp
from .storage.store import store_instance

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Application lifespan — loads the store on startup
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Load store.json into memory at startup, nothing to clean up at shutdown."""
    logger.info("Loading data store …")
    store_instance.load_store()
    logger.info("Data store ready — %d invoices loaded.", len(store_instance.get_invoices()))
    yield
    logger.info("Application shutting down.")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="WhatsApp Collections Agent — Backend",
    description=(
        "REST API for the ProcWing WhatsApp Collections Agent. "
        "Upload an AR sheet and query customer payment schedules."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — allow the local Vite dev server (API_SPEC.md §0 base URL note)
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Exception handlers — every error becomes ErrorResponse (API_SPEC.md §0)
# ---------------------------------------------------------------------------

app.add_exception_handler(AppError, app_error_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)

# ---------------------------------------------------------------------------
# Router registration (prefix = /api per API_SPEC.md)
# ---------------------------------------------------------------------------

app.include_router(health.router, prefix="/api/health", tags=["health"])
app.include_router(upload.router, prefix="/api/upload", tags=["upload"])
app.include_router(invoices.router, prefix="/api/invoices", tags=["invoices"])
app.include_router(customers.router, prefix="/api/customers", tags=["customers"])
# WhatsApp webhook — owned by the WhatsApp agent; placeholder router for now.
app.include_router(whatsapp.router, prefix="/api/whatsapp", tags=["whatsapp"])
