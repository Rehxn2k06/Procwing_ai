# backend/app/business_logic/__init__.py

# This file makes the 'business_logic' directory a Python package.
# It can be used to expose key functions or classes on import,
# or to define package-level variables/constants.

# Importing from modules within this package:
from .ageing import (
    get_today,
    get_current_week,
    compute_ageing_bucket,
    compute_days_overdue,
    compute_is_due_this_week,
    CustomerNotFoundError,
    PaymentSchedule,
    CollectionFollowup,
    CustomerRef,
    InvoiceRecord,
)
from .customer_key import normalize

from .matching import resolve_customer_name, MatchResult

# Importing from reports and render modules to make them available via __init__.py
from .reports import (
    get_payment_schedule,
    get_collection_followup,
)
from .render import (
    format_inr,
    format_date_ddmonyyyy,
    render_payment_schedule_message,
    render_collection_followup_message,
)

# Expose specific functions and classes that are commonly used or represent the API of this package.
# This allows consumers to import them directly from 'app.business_logic', e.g.:
# from app.business_logic import get_today, normalize, resolve_customer_name, render_payment_schedule_message

__all__ = [
    # ageing.py
    "get_today",
    "get_current_week",
    "compute_ageing_bucket",
    "compute_days_overdue",
    "compute_is_due_this_week",
    "CustomerNotFoundError",
    "PaymentSchedule",
    "CollectionFollowup",
    "CustomerRef",
    "InvoiceRecord",
    # customer_key.py
    "normalize",
    # matching.py
    "resolve_customer_name",
    "MatchResult",
    # reports.py
    "get_payment_schedule",
    "get_collection_followup",
    # render.py
    "format_inr",
    "format_date_ddmonyyyy",
    "render_payment_schedule_message",
    "render_collection_followup_message",
]
