# backend/app/business_logic/reports.py

from datetime import date, timedelta
from typing import List, Dict, Any
from dataclasses import dataclass, field
import re

# Import necessary types and functions from other modules
from .ageing import (
    get_today,
    get_current_week,
    compute_ageing_bucket,
    compute_days_overdue,
    compute_is_due_this_week,
    CustomerNotFoundError,
    # Import the dataclasses that represent the return types for these functions
    PaymentSchedule,
    CollectionFollowup,
    CustomerRef,
    InvoiceRecord,
)

__all__ = [
    "get_payment_schedule",
    "get_collection_followup",
]

# --- Report Generation Logic ---

def get_payment_schedule(customer_key: str, invoices: List[InvoiceRecord], today: date) -> PaymentSchedule:
    """
    Generates the payment schedule data for a specific customer.
    This function computes ageing buckets, overdue amounts, and total outstanding based on the provided invoices.
    It returns structured data, not rendered messages or formatted strings.
    """
    customer_invoices = [inv for inv in invoices if inv.customer_key == customer_key]
    
    if not customer_invoices:
        raise CustomerNotFoundError(customer_key)

    total_outstanding = 0.0
    overdue_amount = 0.0
    due_this_week = 0.0
    no_due_date_count = 0
    no_due_date_total = 0.0

    # Initialize ageing buckets with zeros
    ageing_buckets_sum: Dict[str, float] = {
        "90+": 0.0, "61-90": 0.0, "31-60": 0.0, "16-30": 0.0, "0-15": 0.0, "NOT_DUE": 0.0
    }
    
    week_start, week_end = get_current_week(today)

    for inv in customer_invoices:
        total_outstanding += inv.outstanding
        bucket = compute_ageing_bucket(inv.due_date, today)
        # compute_days_overdue is not directly used here as its output is not needed for PaymentSchedule structure.
        is_due_this_week = compute_is_due_this_week(inv.due_date, week_start, week_end)

        if bucket == "NO_DUE_DATE":
            no_due_date_count += 1
            no_due_date_total += inv.outstanding
        elif bucket != "NOT_DUE": # It's an overdue bucket
            overdue_amount += inv.outstanding
            if bucket in ageing_buckets_sum: # Only add to specific overdue buckets
                ageing_buckets_sum[bucket] += inv.outstanding
        
        if is_due_this_week and bucket != "NO_DUE_DATE": # Only count if due this week and not NO_DUE_DATE
            due_this_week += inv.outstanding

    # Combine the overdue sum with specific bucket sums
    # The `overdue` key in final output is sum of all overdue buckets; not recalculated here.
    ageing_breakdown = {
        "overdue": overdue_amount,
        **ageing_buckets_sum # This will merge the specific buckets
    }
    # Ensure all expected buckets are present, even if 0.

    # Extracting display name and SPOC
    # Follow DATABASE_SCHEMA.md §2 for display name logic (most frequent raw name)
    raw_name_counts: Dict[str, int] = {}
    customer_spoc: str | None = None
    
    for inv in customer_invoices:
        raw_name_counts[inv.customer_raw] = raw_name_counts.get(inv.customer_raw, 0) + 1
        if customer_spoc is None and inv.spoc: # Use first found SPOC
            customer_spoc = inv.spoc

    if raw_name_counts:
        display_name = max(raw_name_counts, key=raw_name_counts.get)
    else: # Should not happen if customer_invoices is not empty
        display_name = "Unknown Customer"

    # Format invoice list for the API response (data structure, not rendered message)
    formatted_invoices = []
    for inv in customer_invoices:
        formatted_invoices.append({
            "invoice_no": inv.invoice_no,
            "due_date": inv.due_date.isoformat() if inv.due_date else None, # Keep as ISO string as per API spec
            "outstanding": inv.outstanding
        })

    return PaymentSchedule(
        customer_key=customer_key,
        display_name=display_name,
        spoc=customer_spoc,
        overdue_amount=overdue_amount,
        due_this_week=due_this_week,
        total_outstanding=total_outstanding,
        ageing_breakdown=ageing_breakdown,
        invoices=formatted_invoices,
        no_due_date_count=no_due_date_count,
        no_due_date_total=no_due_date_total
    )


def get_collection_followup(customer_key: str, invoices: List[InvoiceRecord], today: date) -> CollectionFollowup:
    """
    Generates the collection follow-up data for a specific customer.
    Includes a daily breakdown of amounts due. Returns structured data, not rendered messages.
    """
    customer_invoices = [inv for inv in invoices if inv.customer_key == customer_key]
    
    if not customer_invoices:
        raise CustomerNotFoundError(customer_key)

    overdue_amount = 0.0
    due_this_week_flag_sum = 0.0 # Sum of invoices flagged as 'is_due_this_week=True'
    
    week_start, week_end = get_current_week(today)
    
    daily_breakdown_raw: Dict[date, float] = {} # Store amounts per specific date
    
    # Initialize for all 5 weekdays + Monday overdue snapshot
    current_date = week_start
    while current_date <= week_end:
        daily_breakdown_raw[current_date] = 0.0
        current_date += timedelta(days=1)
    
    # Calculate overdue as of Monday of this week
    overdue_as_of_monday_amount = 0.0
    for inv in customer_invoices:
        # Check if invoice's due date is before the start of the current week
        if inv.due_date is not None and inv.due_date < week_start:
            overdue_as_of_monday_amount += inv.outstanding
        
        # Check for specific daily dues within the week
        if inv.due_date in daily_breakdown_raw:
            daily_breakdown_raw[inv.due_date] += inv.outstanding
            # Summing up all invoices due within the Mon-Fri window for the 'due_this_week' flag field
            if compute_is_due_this_week(inv.due_date, week_start, week_end):
                 due_this_week_flag_sum += inv.outstanding
        
    # Calculate total overdue amount (sum of all overdue buckets)
    for inv in customer_invoices:
        bucket = compute_ageing_bucket(inv.due_date, today)
        if bucket != "NOT_DUE" and bucket != "NO_DUE_DATE":
            overdue_amount += inv.outstanding

    # Format the daily breakdown list (structured data, not rendered message)
    formatted_daily_breakdown = []
    
    # `total_collection_target`: Overdue as of Monday + sum of amounts due each day Mon-Fri.
    sum_of_daily_amounts = sum(daily_breakdown_raw.values())
    total_collection_target = overdue_as_of_monday_amount + sum_of_daily_amounts
    
    # Entry 1: "Overdue on {Monday's date}"
    # Use strftime directly for label formatting as per API spec (§7)
    formatted_daily_breakdown.append({
        "label": f"Overdue on {week_start.strftime('%d-%b-%Y')}", # DD-Mon-YYYY format
        "date": None, # As per API spec, this label has null date
        "amount": overdue_as_of_monday_amount
    })
    
    # Entries 2-6: Weekdays (Mon-Fri)
    current_date = week_start
    while current_date <= week_end:
        # Format date to DD-Mon-YY for label string as per API spec (§7)
        formatted_daily_breakdown.append({
            "label": current_date.strftime('%d-%b-%y'), # DD-Mon-YY format
            "date": current_date.isoformat(), # ISO format for date field
            "amount": daily_breakdown_raw.get(current_date, 0.0)
        })
        current_date += timedelta(days=1)
        
    # Entry 7: "Total Dues By {Friday's date}"
    formatted_daily_breakdown.append({
        "label": f"Total Dues By {week_end.strftime('%d-%b-%Y')}", # DD-Mon-YYYY format
        "date": None, # As per API spec
        "amount": total_collection_target
    })

    # Extracting display name and SPOC (following DATABASE_SCHEMA.md §2 logic)
    raw_name_counts: Dict[str, int] = {}
    customer_spoc: str | None = None
    for inv in customer_invoices:
        raw_name_counts[inv.customer_raw] = raw_name_counts.get(inv.customer_raw, 0) + 1
        if customer_spoc is None and inv.spoc:
            customer_spoc = inv.spoc

    if raw_name_counts:
        display_name = max(raw_name_counts, key=raw_name_counts.get)
    else: 
        display_name = "Unknown Customer"
        
    # Format invoice list for the output structure
    formatted_invoices = []
    for inv in customer_invoices:
        formatted_invoices.append({
            "invoice_no": inv.invoice_no,
            "due_date": inv.due_date.isoformat() if inv.due_date else None,
            "outstanding": inv.outstanding
        })

    return CollectionFollowup(
        customer_key=customer_key,
        display_name=display_name,
        spoc=customer_spoc,
        overdue_amount=overdue_amount,
        due_this_week=due_this_week_flag_sum,
        week_start=week_start,
        week_end=week_end,
        total_collection_target=total_collection_target,
        daily_breakdown=formatted_daily_breakdown,
        invoices=formatted_invoices
    )
