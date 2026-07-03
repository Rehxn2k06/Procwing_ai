# backend/app/business_logic/render.py

from datetime import date
from typing import List
from dataclasses import dataclass, field
import re

# Import necessary types and functions from other modules
from .ageing import PaymentSchedule, CollectionFollowup

# Maximum number of individual invoice lines to include in a WhatsApp message.
# Twilio Sandbox enforces a ~1,600-character limit per outbound message; listing
# every invoice for customers with 15-25 invoices easily exceeds that.  We show
# the first MAX_INVOICE_LINES invoices and append a "...and X more" summary line
# so the key totals and ageing breakdown are always fully visible.
_MAX_INVOICE_LINES: int = 7

# --- Formatting Helper Functions ---

def format_inr(amount: float) -> str:
    """
    Formats a float amount into an Indian Rupee string with comma separators.
    Example: 1234567.89 -> "₹12,34,567.89"
    """
    # Standard Python formatting does not inherently support Indian comma grouping.
    # We manually format for Indian numbering system:
    # 1. Split into integer and decimal parts.
    # 2. Process the integer part from right to left. Insert a comma after the first 3 digits.
    # 3. Then, insert a comma after every 2 digits thereafter.
    
    formatted_str = f"{amount:.2f}" # Basic formatting with thousands separator
    
    if "." in formatted_str:
        integer_part, decimal_part = formatted_str.split(".", 1)
        decimal_part = f".{decimal_part}"
    else:
        integer_part = formatted_str
        decimal_part = ""
        
    # Remove the initial comma from basic formatting if it exists
    if integer_part.startswith(","):
        integer_part = integer_part[1:]
        
    # Process the integer part for Indian grouping
    n = len(integer_part)
    if n <= 3:
        return f"₹{integer_part}{decimal_part}"
    
    # Take the last 3 digits
    last_three = integer_part[-3:]
    # Remaining digits to be formatted with groups of 2
    remaining_digits = integer_part[:-3]
    
    # Group the remaining digits by 2, from right to left
    groups = []
    while remaining_digits:
        groups.append(remaining_digits[-2:])
        remaining_digits = remaining_digits[:-2]

    # Reverse the groups and join with commas
    formatted_remaining = ",".join(groups[::-1])
    
    # Combine ₹, the remaining formatted digits, and the last three digits
    return f"₹{formatted_remaining}{last_three}{decimal_part}"


def format_date_ddmonyyyy(d: date) -> str:
    """
    Formats a date object into DD-Mon-YY string format.
    Example: date(2026, 7, 4) -> "04-Jul-26"
    """
    # %d for day with leading zero, %b for abbreviated month name, %y for year without century
    return d.strftime('%d-%b-%y') # This format directly produces e.g. "04-Jul-26"

# --- Message Rendering ---

def render_payment_schedule_message(schedule: PaymentSchedule) -> str:
    """
    Renders the payment schedule data into a WhatsApp-formatted message string.
    Follows patterns from CODING_STANDARDS.md §4.
    """
    message_lines = []
    
    # Header
    message_lines.append(f"*Weekly Payment Reminder – {schedule.display_name}*")
    message_lines.append("") # Blank line for spacing
    
    # Introduction/Greeting
    message_lines.append("Dear Sir/Madam,")
    message_lines.append("")
    
    # Overdue Section
    if schedule.overdue_amount > 0:
        message_lines.append(f"*Overdue Amount:* {format_inr(schedule.overdue_amount)}")
        message_lines.append("Your account is overdue. Please find the breakdown below:")
        message_lines.append("")

        # Ageing Breakdown (as aligned plain text)
        message_lines.append("*Ageing Breakdown:*")
        label_width = 10 # Sufficient width for bucket labels like "61-90" or "overdue"
        amount_width = 15 # Sufficient space for formatted INR amounts.
        
        # Define the order for the breakdown, ensuring "overdue" is first.
        ordered_buckets = ["overdue", "90+", "61-90", "31-60", "16-30", "0-15"]
        
        for bucket in ordered_buckets:
            amount = schedule.ageing_breakdown.get(bucket, 0.0)
            if amount > 0: # Only show buckets with outstanding amounts
                # Format amount, left-align label, right-align amount
                message_lines.append(f"{bucket.ljust(label_width)} {format_inr(amount).rjust(amount_width)}")
        message_lines.append("")
    elif schedule.due_this_week > 0:
        # If not overdue but due this week, mention that.
        message_lines.append(f"*Due This Week:* {format_inr(schedule.due_this_week)}")
        message_lines.append("Please find the details below:")
        message_lines.append("")
    else:
        # Customer has nothing overdue and nothing due this week
        message_lines.append("You have no outstanding amounts due.")
        message_lines.append("Thank you for your prompt attention.")
        message_lines.append("")
        return "\n".join(message_lines) # Early exit if no dues

    # Invoice List (append if there was overdue amount or due this week amount).
    # Capped at _MAX_INVOICE_LINES to stay within Twilio's message size limit.
    if schedule.invoices:
        message_lines.append("*Invoice Details:*")
        shown = schedule.invoices[:_MAX_INVOICE_LINES]
        remaining = len(schedule.invoices) - len(shown)
        for inv in shown:
            invoice_no = inv.get("invoice_no", "N/A")
            due_date_str = inv.get("due_date")
            outstanding = inv.get("outstanding", 0.0)

            due_line = f"Invoice No: {invoice_no}"
            if due_date_str:
                # Format due date if available
                try:
                    due_date = date.fromisoformat(due_date_str)
                    due_line += f", Due: {format_date_ddmonyyyy(due_date)}"
                except ValueError:
                    due_line += f", Due: {due_date_str}"  # Fallback if parsing fails

            due_line += f", Outstanding: {format_inr(outstanding)}"
            message_lines.append(due_line)
        if remaining > 0:
            message_lines.append(f"...and {remaining} more invoice(s). See portal for full list.")
        message_lines.append("")  # Blank line after invoice list

    # Handle NO_DUE_DATE if present (important edge case)
    if schedule.no_due_date_count > 0:
        message_lines.append(f"*Note: {schedule.no_due_date_count} invoice(s) with no due date total {format_inr(schedule.no_due_date_total)}.*")
        message_lines.append("Please clarify or settle these at your earliest convenience.")
        message_lines.append("")

    # Closing
    message_lines.append("Thank you for your attention.")
    message_lines.append("")
    message_lines.append("Sincerely,")
    message_lines.append("_ProcWing Collections Team_") # Use underscore for italics per CODING_STANDARDS
    
    return "\n".join(message_lines)


def render_collection_followup_message(followup: CollectionFollowup) -> str:
    """
    Renders the collection follow-up data into a WhatsApp-formatted message string.
    Follows patterns from CODING_STANDARDS.md §4.
    """
    message_lines = []
    
    # Header
    message_lines.append(f"*Collection Follow-up – {followup.display_name}*")
    message_lines.append("")
    
    # Introduction/Greeting
    message_lines.append("Dear Sir/Madam,")
    message_lines.append("")
    
    # Overdue and Due This Week Summary
    message_lines.append(f"We are writing to follow up on your outstanding balance of {format_inr(followup.overdue_amount)}.")
    # Add a line for due this week only if it's relevant and distinct from overdue
    if followup.due_this_week > 0 and followup.overdue_amount != followup.due_this_week: # Check for distinctness to avoid redundancy
         message_lines.append(f"An additional {format_inr(followup.due_this_week)} is due by the end of this week ({format_date_ddmonyyyy(followup.week_end)}).")
    message_lines.append(f"Your total outstanding amount is {format_inr(followup.total_collection_target)}.")
    message_lines.append("")

    # Daily Breakdown (Task 2 - structured as aligned plain text)
    message_lines.append("*Collection Target Breakdown:*")
    label_width = 25 # Generous width for labels like "Overdue on DD-Mon-YYYY"
    amount_width = 15 # Sufficient space for INR amounts.
    
    for entry in followup.daily_breakdown:
        label = entry.get("label", "Unknown Date")
        amount = entry.get("amount", 0.0)
        # Only display entries with a non-zero amount, except for the 'Total Dues By...' line which should always show
        if amount > 0 or "Total Dues By" in label:
            # Format amount and align right, left-align label
            message_lines.append(f"{label.ljust(label_width)} {format_inr(amount).rjust(amount_width)}")
    message_lines.append("") # Blank line after breakdown
    
    # Invoice List.
    # Capped at _MAX_INVOICE_LINES to stay within Twilio's message size limit.
    if followup.invoices:
        message_lines.append("*Outstanding Invoices:*")
        shown = followup.invoices[:_MAX_INVOICE_LINES]
        remaining = len(followup.invoices) - len(shown)
        for inv in shown:
            invoice_no = inv.get("invoice_no", "N/A")
            due_date_str = inv.get("due_date")
            outstanding = inv.get("outstanding", 0.0)

            due_line = f"Invoice No: {invoice_no}"
            if due_date_str:
                try:
                    due_date = date.fromisoformat(due_date_str)
                    due_line += f", Due: {format_date_ddmonyyyy(due_date)}"
                except ValueError:
                    due_line += f", Due: {due_date_str}"  # Fallback

            due_line += f", Outstanding: {format_inr(outstanding)}"
            message_lines.append(due_line)
        if remaining > 0:
            message_lines.append(f"...and {remaining} more invoice(s). See portal for full list.")
        message_lines.append("")  # Blank line after invoice list

    # Closing
    message_lines.append("We kindly request you to settle this amount at your earliest convenience.")
    message_lines.append("Thank you for your attention.")
    message_lines.append("")
    message_lines.append("Sincerely,")
    message_lines.append("_ProcWing Collections Team_") # Use underscore for italics per CODING_STANDARDS
    
    return "\n".join(message_lines)

# __all__ definition is handled in __init__.py, listing functions exposed at package level.
# Ensure __init__.py is updated if new public functions are added here.

# Example usage (for testing purposes)
if __name__ == "__main__":
    # Mock data for Payment Schedule
    mock_payment_schedule = PaymentSchedule(
        customer_key="abc",
        display_name="ABC Pvt Ltd",
        spoc="Rahul Sharma",
        overdue_amount=100000.0,
        due_this_week=25000.0,
        total_outstanding=125000.0,
        ageing_breakdown={"overdue": 100000.0, "90+": 50000.0, "61-90": 0.0, "31-60": 0.0, "16-30": 0.0, "0-15": 50000.0, "NOT_DUE": 25000.0},
        invoices=[
            {"invoice_no": "INV-1001", "due_date": "2026-04-20", "outstanding": 50000.0},
            {"invoice_no": "INV-1002", "due_date": "2026-05-10", "outstanding": 50000.0},
            {"invoice_no": "INV-1003", "due_date": "2026-07-15", "outstanding": 25000.0},
        ],
        no_due_date_count=0,
        no_due_date_total=0.0
    )

    print("--- Rendering Payment Schedule Message ---")
    rendered_payment = render_payment_schedule_message(mock_payment_schedule)
    print(rendered_payment)
    print("-" * 30)

    # Mock data for Collection Followup
    # Let's adjust mock data for better testing of conditions
    # Example: Overdue amount is higher, and due this week amount is separate.
    mock_collection_followup = CollectionFollowup(
        customer_key="xyz",
        display_name="XYZ Corp",
        spoc="Rajesh Kumar",
        overdue_amount=75000.0, # Total overdue irrespective of date
        due_this_week=25000.0, # Specifically items due Mon-Fri this week
        week_start=date(2026, 6, 30), # Monday of current week
        week_end=date(2026, 7, 4),   # Friday of current week
        total_collection_target=100000.0, # Overdue on Monday (75k) + Sum of daily amounts (25k this week) = 100k
        daily_breakdown=[
            {"label": "Overdue on 30-Jun-2026", "date": None, "amount": 75000.0}, # Invoice due June 25th, so overdue on Monday
            {"label": "30-Jun-26", "date": "2026-06-30", "amount": 25000.0}, # Invoice due June 30th (Monday)
            {"label": "01-Jul-26", "date": "2026-07-01", "amount": 0.0},
            {"label": "02-Jul-26", "date": "2026-07-02", "amount": 0.0},
            {"label": "03-Jul-26", "date": "2026-07-03", "amount": 0.0},
            {"label": "04-Jul-26", "date": "2026-07-04", "amount": 0.0},
            {"label": "Total Dues By 04-Jul-2026", "date": None, "amount": 100000.0} # Cumulative total
        ],
        invoices=[
            {"invoice_no": "INV-2001", "due_date": "2026-06-25", "outstanding": 75000.0}, # Overdue from last week
            {"invoice_no": "INV-2002", "due_date": "2026-06-30", "outstanding": 25000.0}  # Due Monday this week
        ]
    )

    print("\n--- Rendering Collection Followup Message ---")
    rendered_collection = render_collection_followup_message(mock_collection_followup)
    print(rendered_collection)
    print("-" * 30)
    
    # Mock data for customer with no dues
    mock_payment_schedule_no_dues = PaymentSchedule(
        customer_key="paid",
        display_name="Paid Customer",
        spoc="Accounts",
        overdue_amount=0.0,
        due_this_week=0.0,
        total_outstanding=0.0, # Or could be non-zero if fully paid invoices remain
        ageing_breakdown={"overdue": 0.0, "90+": 0.0, "61-90": 0.0, "31-60": 0.0, "16-30": 0.0, "0-15": 0.0, "NOT_DUE": 0.0},
        invoices=[], # No outstanding invoices
        no_due_date_count=0,
        no_due_date_total=0.0
    )
    
    print("\n--- Rendering Payment Schedule Message (No Dues) ---")
    rendered_no_dues = render_payment_schedule_message(mock_payment_schedule_no_dues)
    print(rendered_no_dues)
    print("-" * 30)
