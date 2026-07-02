# backend/app/business_logic/ageing.py

from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo
from dataclasses import dataclass

# Constants and Configurations
IST = ZoneInfo("Asia/Kolkata")
MATCH_THRESHOLD = 70  # As per AGENT_PROMPT_BUSINESS_LOGIC.md §2

# --- Date and Week Logic ---


def get_today() -> date:
    """
    Single source of truth for 'today' in IST timezone.
    Never call date.today() directly elsewhere.
    """
    now = datetime.now(IST)
    return now.date()


def get_current_week(today: date) -> tuple[date, date]:
    """
    Calculates the start (Monday) and end (Friday) of the current week,
    based on the ISO week number containing 'today'.
    Ignores Saturday and Sunday for week boundaries.
    """
    # ISO weekday: Monday is 1, Sunday is 7
    # Calculate Monday of the current ISO week
    # `today.isoweekday() - 1` gives days to subtract to get to Monday
    week_start = today - timedelta(days=today.isoweekday() - 1)
    # Friday is 4 days after Monday
    week_end = week_start + timedelta(days=4)
    return week_start, week_end


# --- Ageing Computations ---


def compute_ageing_bucket(due_date: date | None, today: date) -> str:
    """
    Computes the ageing bucket for an invoice based on its due date and today's date.
    Matches the buckets defined in DATABASE_SCHEMA.md §3.
    """
    if due_date is None:
        return "NO_DUE_DATE"

    if due_date >= today:
        return "NOT_DUE"

    days_overdue = (today - due_date).days

    if 1 <= days_overdue <= 15:
        return "0-15"
    elif 16 <= days_overdue <= 30:
        return "16-30"
    elif 31 <= days_overdue <= 60:
        return "31-60"
    elif 61 <= days_overdue <= 90:
        return "61-90"
    else:  # days_overdue >= 91
        return "90+"


def compute_days_overdue(due_date: date | None, today: date) -> int | None:
    """
    Computes the number of days an invoice is overdue. Returns None if not overdue
    or if there's no due date.
    """
    if due_date is None or due_date >= today:
        return None

    return (today - due_date).days


def compute_is_due_this_week(
    due_date: date | None, week_start: date, week_end: date
) -> bool:
    """
    Checks if an invoice's due date falls within the current week (Monday to Friday).
    """
    if due_date is None:
        return False

    # The week_end is Friday, so we check if due_date <= week_end
    # and if it's within the current week's Monday to Friday range.
    # This also correctly handles cases where due_date might be in the past but still within this Mon-Fri window.
    return week_start <= due_date <= week_end


# --- Utility Types ---
# These would typically be in a separate types/models file if the project were larger,
# but for this specific agent's scope, defining them here is acceptable for unit testability.
# In a real scenario, these would likely be imported from app.models.common or similar.
# For this assignment, we define minimal dataclasses here to facilitate type hints.


@dataclass
class CustomerRef:
    customer_key: str
    display_name: str


@dataclass
class InvoiceRecord:
    id: str
    customer_raw: str
    customer_key: str
    spoc: str | None
    invoice_no: str
    invoice_date: date | None
    due_date: date | None
    inv_amount: float
    received: float
    outstanding: float


@dataclass
class AgeingSummary:
    bucket: str
    count: int
    total_outstanding: float


@dataclass
class PaymentSchedule:
    customer_key: str
    display_name: str
    spoc: str | None
    overdue_amount: float
    due_this_week: float
    total_outstanding: float
    ageing_breakdown: dict[str, float]  # e.g. {"90+": 0.0, "61-90": 25000.0, ...}
    invoices: list[
        dict
    ]  # Minimal invoice info: {"invoice_no": str, "due_date": str | None, "outstanding": float}
    no_due_date_count: int
    no_due_date_total: float


@dataclass
class CollectionFollowup:
    customer_key: str
    display_name: str
    spoc: str | None
    overdue_amount: float
    due_this_week: float
    week_start: date
    week_end: date
    total_collection_target: float  # Sum of overdue_amount and due_this_week amounts
    daily_breakdown: list[
        dict
    ]  # [{"label": str, "date": date | None, "amount": float}]
    invoices: list[
        dict
    ]  # Minimal invoice info: {"invoice_no": str, "due_date": str | None, "outstanding": float}


class CustomerNotFoundError(Exception):
    """Custom exception for when a customer key is not found."""

    def __init__(self, customer_key: str):
        self.customer_key = customer_key
        super().__init__(f"Customer with key '{customer_key}' not found.")


# --- Report Generation ---


def get_payment_schedule(
    customer_key: str, invoices: list[InvoiceRecord], today: date
) -> PaymentSchedule:
    """
    Generates the payment schedule data for a specific customer.
    This function computes ageing buckets, overdue amounts, and total outstanding based on the provided invoices.
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
    ageing_buckets_sum: dict[str, float] = {
        "90+": 0.0,
        "61-90": 0.0,
        "31-60": 0.0,
        "16-30": 0.0,
        "0-15": 0.0,
        "NOT_DUE": 0.0,
    }

    week_start, week_end = get_current_week(today)

    for inv in customer_invoices:
        total_outstanding += inv.outstanding
        bucket = compute_ageing_bucket(inv.due_date, today)
        # Removed unused variable assignment: days_overdue = compute_days_overdue(inv.due_date, today)
        is_due_this_week = compute_is_due_this_week(inv.due_date, week_start, week_end)

        if bucket == "NO_DUE_DATE":
            no_due_date_count += 1
            no_due_date_total += inv.outstanding
        elif bucket != "NOT_DUE":  # It's an overdue bucket
            overdue_amount += inv.outstanding
            if bucket in ageing_buckets_sum:  # Only add to specific overdue buckets
                ageing_buckets_sum[bucket] += inv.outstanding

        if (
            is_due_this_week and bucket != "NO_DUE_DATE"
        ):  # Only count if due this week and not NO_DUE_DATE
            due_this_week += inv.outstanding

    # Combine the overdue sum with specific bucket sums
    # The `overdue` key in final output is sum of all overdue buckets; not recalculated here.
    # The `overdue_amount` is calculated above.
    ageing_breakdown = {
        "overdue": overdue_amount,
        **ageing_buckets_sum,  # This will merge the specific buckets
    }
    # Ensure all expected buckets are present, even if 0.
    # "NOT_DUE" and "NO_DUE_DATE" are handled separately in database schema summary.
    # The prompt only mentions those 6 keys for 'ageing_breakdown' structure.

    # Extracting display name and SPOC based on DATABASE_SCHEMA.md §2 logic for grouping
    # For a single customer, we assume they are unique or we use the first encountered display name.
    # A more robust approach would involve looking at all raw names and picking the most frequent.
    # For this scope, we use the first invoice's details as a proxy if customer_key matches.
    raw_name_counts = {}
    customer_spoc = None

    for inv in customer_invoices:
        raw_name_counts[inv.customer_raw] = raw_name_counts.get(inv.customer_raw, 0) + 1
        if customer_spoc is None and inv.spoc:
            customer_spoc = inv.spoc

    if raw_name_counts:
        display_name = max(raw_name_counts, key=raw_name_counts.get)
    else:  # Should not happen if customer_invoices is not empty
        display_name = "Unknown Customer"

    # Format invoice list for the API response
    formatted_invoices = []
    for inv in customer_invoices:
        formatted_invoices.append(
            {
                "invoice_no": inv.invoice_no,
                "due_date": inv.due_date.isoformat() if inv.due_date else None,
                "outstanding": inv.outstanding,
            }
        )

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
        no_due_date_total=no_due_date_total,
    )


def get_collection_followup(
    customer_key: str, invoices: list[InvoiceRecord], today: date
) -> CollectionFollowup:
    """
    Generates the collection follow-up data for a specific customer.
    Includes a daily breakdown of amounts due.
    """
    customer_invoices = [inv for inv in invoices if inv.customer_key == customer_key]

    if not customer_invoices:
        raise CustomerNotFoundError(customer_key)

    overdue_amount = 0.0
    due_this_week_flag_sum = 0.0  # This field in API Spec §7 seems to refer to total outstanding of invoices strictly due this week (Mon-Fri)

    week_start, week_end = get_current_week(today)

    daily_breakdown_raw: dict[date, float] = {}  # Store amounts per specific date

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
            if compute_is_due_this_week(
                inv.due_date, week_start, week_end
            ):  # Re-using logic to ensure consistency
                due_this_week_flag_sum += inv.outstanding

    # Calculate total overdue amount (sum of all overdue buckets)
    for inv in customer_invoices:
        bucket = compute_ageing_bucket(inv.due_date, today)
        if bucket != "NOT_DUE" and bucket != "NO_DUE_DATE":
            overdue_amount += inv.outstanding

    # Format the daily breakdown list
    formatted_daily_breakdown = []
    # `total_collection_target` is "Overdue on Monday" + sum of the 5 daily entries for payments due *that day*.
    # The prompt implies `due_this_week` in `CollectionFollowup` might be sum of daily entries across the week.
    # However, DATABASE_SCHEMA.md §3 explicitly defines `is_due_this_week` a boolean per invoice.
    # PROJECT_SPEC.md §4: "Due This Week = sum of Outstanding where Due Date falls in the current Mon–Fri window."
    # This suggests `due_this_week` is the sum of all invoices flagged `is_due_this_week=True`.
    # The total_collection_target seems to be a specific calculation for a target goal.
    # Let's recalculate total_collection_target: it's overdue_as_of_monday_amount + sum of amounts due Mon-Fri.
    sum_of_daily_amounts = sum(daily_breakdown_raw.values())
    total_collection_target = overdue_as_of_monday_amount + sum_of_daily_amounts

    # Entry 1: "Overdue on {Monday's date}"
    formatted_daily_breakdown.append(
        {
            "label": f"Overdue on {week_start.strftime('%d-%b-%Y')}",  # Format as DD-Mon-YYYY
            "date": None,  # As per API spec, this label has null date
            "amount": overdue_as_of_monday_amount,
        }
    )

    # Entries 2-6: Weekdays (Mon-Fri)
    current_date = week_start
    while current_date <= week_end:
        # Format date to DD-Mon-YY as per example in API_SPEC.md §7
        # Manual formatting to match "04-Jul-26" or similar, avoiding locale specific formatting like %y which might add space.
        # Example in prompt: "02-Jul-26"
        day_str = current_date.strftime("%d")
        month_str = current_date.strftime("%b")
        year_str = current_date.strftime("%y")
        formatted_date_str = f"{day_str}-{month_str}-{year_str}"

        formatted_daily_breakdown.append(
            {
                "label": formatted_date_str,
                "date": current_date.isoformat(),
                "amount": daily_breakdown_raw.get(current_date, 0.0),
            }
        )
        current_date += timedelta(days=1)

    # Entry 7: "Total Dues By {Friday's date}"
    formatted_daily_breakdown.append(
        {
            "label": f"Total Dues By {week_end.strftime('%d-%b-%Y')}",  # Format as DD-Mon-YYYY
            "date": None,  # As per API spec
            "amount": total_collection_target,
        }
    )

    # Extracting display name and SPOC
    raw_name_counts = {}
    customer_spoc = None
    for inv in customer_invoices:
        raw_name_counts[inv.customer_raw] = raw_name_counts.get(inv.customer_raw, 0) + 1
        if customer_spoc is None and inv.spoc:
            customer_spoc = inv.spoc

    if raw_name_counts:
        display_name = max(raw_name_counts, key=raw_name_counts.get)
    else:
        display_name = "Unknown Customer"

    # Format invoice list
    formatted_invoices = []
    for inv in customer_invoices:
        formatted_invoices.append(
            {
                "invoice_no": inv.invoice_no,
                "due_date": inv.due_date.isoformat() if inv.due_date else None,
                "outstanding": inv.outstanding,
            }
        )

    return CollectionFollowup(
        customer_key=customer_key,
        display_name=display_name,
        spoc=customer_spoc,
        overdue_amount=overdue_amount,
        due_this_week=due_this_week_flag_sum,  # This is the sum of invoices flagged 'is_due_this_week=True' across all days Mon-Fri.
        week_start=week_start,
        week_end=week_end,
        total_collection_target=total_collection_target,
        daily_breakdown=formatted_daily_breakdown,
        invoices=formatted_invoices,
    )


# Example usage (for testing purposes, not part of released code)
if __name__ == "__main__":
    # Mock data
    today = date(2026, 7, 2)  # Thursday
    week_start, week_end = get_current_week(today)

    sample_invoices: list[InvoiceRecord] = [
        # Invoice 1: Overdue > 90 days
        InvoiceRecord(
            id="inv1",
            customer_raw="ABC Pvt Ltd",
            customer_key="abc",
            spoc="Rahul",
            invoice_no="INV-1001",
            invoice_date=date(2026, 4, 15),
            due_date=date(2026, 4, 20),
            inv_amount=50000.0,
            received=0.0,
            outstanding=50000.0,
        ),
        # Invoice 2: Overdue 61-90 days
        InvoiceRecord(
            id="inv2",
            customer_raw="ABC Pvt Ltd",
            customer_key="abc",
            spoc="Rahul",
            invoice_no="INV-1002",
            invoice_date=date(2026, 5, 1),
            due_date=date(2026, 5, 10),
            inv_amount=40000.0,
            received=0.0,
            outstanding=40000.0,
        ),
        # Invoice 3: Not due yet
        InvoiceRecord(
            id="inv3",
            customer_raw="ABC Pvt Ltd",
            customer_key="abc",
            spoc="Rahul",
            invoice_no="INV-1003",
            invoice_date=date(2026, 6, 15),
            due_date=date(2026, 7, 15),
            inv_amount=30000.0,
            received=0.0,
            outstanding=30000.0,
        ),
        # Invoice 4: Due this week (Wednesday - July 3rd)
        InvoiceRecord(
            id="inv4",
            customer_raw="ABC Pvt Ltd",
            customer_key="abc",
            spoc="Rahul",
            invoice_no="INV-1004",
            invoice_date=date(2026, 6, 30),
            due_date=date(2026, 7, 3),
            inv_amount=20000.0,
            received=0.0,
            outstanding=20000.0,
        ),
        # Invoice 5: Due last week but still overdue (June 25th). Not due this week.
        InvoiceRecord(
            id="inv5",
            customer_raw="ABC Pvt Ltd",
            customer_key="abc",
            spoc="Rahul",
            invoice_no="INV-1005",
            invoice_date=date(2026, 6, 20),
            due_date=date(2026, 6, 25),
            inv_amount=10000.0,
            received=0.0,
            outstanding=10000.0,
        ),
        # Invoice 6: No due date
        InvoiceRecord(
            id="inv6",
            customer_raw="ABC Pvt Ltd",
            customer_key="abc",
            spoc="Rahul",
            invoice_no="INV-1006",
            invoice_date=date(2026, 6, 1),
            due_date=None,
            inv_amount=15000.0,
            received=0.0,
            outstanding=15000.0,
        ),
        # Invoice 7: Different customer - due June 30th (Monday of current week)
        InvoiceRecord(
            id="inv7",
            customer_raw="XYZ Corp",
            customer_key="xyz",
            spoc="Raj",
            invoice_no="INV-2001",
            invoice_date=date(2026, 6, 10),
            due_date=date(2026, 6, 30),
            inv_amount=25000.0,
            received=0.0,
            outstanding=25000.0,
        ),
    ]

    print(f"Today: {today}, Week Start: {week_start}, Week End: {week_end}")

    # Test Payment Schedule
    try:
        payment_schedule = get_payment_schedule("abc", sample_invoices, today)
        print("\n--- Payment Schedule for ABC ---")
        print(
            f"Customer: {payment_schedule.display_name} ({payment_schedule.customer_key})"
        )
        print(f"SPOC: {payment_schedule.spoc}")
        print(f"Overdue Amount: {payment_schedule.overdue_amount}")
        print(f"Due This Week: {payment_schedule.due_this_week}")
        print(f"Total Outstanding: {payment_schedule.total_outstanding}")
        print(f"Ageing Breakdown: {payment_schedule.ageing_breakdown}")
        print(
            f"No Due Date Count: {payment_schedule.no_due_date_count}, Total: {payment_schedule.no_due_date_total}"
        )
        print("Invoices:")
        for inv in payment_schedule.invoices:
            print(
                f"  - {inv['invoice_no']} (Due: {inv['due_date']}, Outstanding: {inv['outstanding']})"
            )
    except CustomerNotFoundError as e:
        print(f"Error getting payment schedule: {e}")

    # Test Collection Followup
    try:
        collection_followup = get_collection_followup("abc", sample_invoices, today)
        print("\n--- Collection Followup for ABC ---")
        print(
            f"Customer: {collection_followup.display_name} ({collection_followup.customer_key})"
        )
        print(f"SPOC: {collection_followup.spoc}")
        print(f"Overdue Amount (Total): {collection_followup.overdue_amount}")
        print(f"Due This Week (Flagged Sum): {collection_followup.due_this_week}")
        print(f"Total Collection Target: {collection_followup.total_collection_target}")
        print(
            f"Week Start: {collection_followup.week_start}, Week End: {collection_followup.week_end}"
        )
        print("Daily Breakdown:")
        for entry in collection_followup.daily_breakdown:
            print(f"  - {entry['label']}: {entry['amount']} (Date: {entry['date']})")
        print("Invoices:")
        for inv in collection_followup.invoices:
            print(
                f"  - {inv['invoice_no']} (Due: {inv['due_date']}, Outstanding: {inv['outstanding']})"
            )

    except CustomerNotFoundError as e:
        print(f"Error getting collection followup: {e}")

    # Test Collection Followup for XYZ customer
    try:
        collection_followup_xyz = get_collection_followup("xyz", sample_invoices, today)
        print("\n--- Collection Followup for XYZ ---")
        print(
            f"Customer: {collection_followup_xyz.display_name} ({collection_followup_xyz.customer_key})"
        )
        print(
            f"Overdue Amount (Total): {collection_followup_xyz.overdue_amount}"
        )  # Should be 25k
        print(
            f"Due This Week (Flagged Sum): {collection_followup_xyz.due_this_week}"
        )  # Should be 25k (due June 30th)
        print(
            f"Total Collection Target: {collection_followup_xyz.total_collection_target}"
        )  # Should be 25k (overdue_as_of_monday=0, sum_of_daily_amounts=25k)
        print("Daily Breakdown:")
        for entry in collection_followup_xyz.daily_breakdown:
            print(f"  - {entry['label']}: {entry['amount']} (Date: {entry['date']})")

    except CustomerNotFoundError as e:
        print(f"Error getting collection followup for XYZ: {e}")

    # Test Customer Not Found
    try:
        get_payment_schedule("nonexistent", sample_invoices, today)
    except CustomerNotFoundError as e:
        print(f"\nSuccessfully caught expected error: {e}")
