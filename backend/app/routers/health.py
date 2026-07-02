"""backend/app/routers/health.py — GET /api/health."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from ..models.schemas import HealthCheckResponse
from ..storage.store import store_instance

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=HealthCheckResponse)
async def health_check() -> HealthCheckResponse:
    """Return service health and the number of invoices currently loaded."""
    invoices: list = store_instance.get_invoices()
    return HealthCheckResponse(status="ok", invoices_loaded=len(invoices))
