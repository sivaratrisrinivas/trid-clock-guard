"""TRID timing rules. Each function names the section it implements."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from .calendars import Calendar, SpecificCalendar, add_business_days

SPECIFIC = SpecificCalendar()


def local_date(ts: datetime, tz: str) -> date:
    """Calendar date of an event in the lender's time zone. Reg Z has no
    time-of-day cutoff for receiving an application; the day it was received
    is the day that counts. We read that day in the lender's local time so a
    late-evening Pacific application is not pushed to the next UTC day.
    (Design choice, not a regulatory rule.)"""
    if ts.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return ts.astimezone(ZoneInfo(tz)).date()


def le_due_date(application_date: date, general: Calendar) -> date:
    """12 CFR 1026.19(e)(1)(iii)(A): deliver or place the Loan Estimate in the
    mail not later than the third business day after the creditor receives
    the application. "Business day" here is the GENERAL definition
    (comment 19(e)(1)(iii)-1; 1026.2(a)(6))."""
    return add_business_days(application_date, 3, general)


def deemed_receipt_date(sent_date: date, method: str) -> date:
    """12 CFR 1026.19(e)(1)(iv): if not provided in person, the consumer is
    considered to have received the LE three business days after it is
    delivered or placed in the mail. Applies to email too (comment
    19(e)(1)(iv)-2). Uses the SPECIFIC definition (listed in 1026.2(a)(6))."""
    if method == "in_person":
        return sent_date
    if method not in ("mail", "email"):
        raise ValueError(method)
    return add_business_days(sent_date, 3, SPECIFIC)


def earliest_consummation_date(le_delivered_or_mailed: date) -> date:
    """12 CFR 1026.19(e)(1)(iii)(B): LE delivered or mailed not later than the
    seventh business day before consummation, SPECIFIC definition. Comment
    19(e)(1)(iii)-2: mailed Mon June 1 -> consummation on or after Tue June 9."""
    return add_business_days(le_delivered_or_mailed, 7, SPECIFIC)
