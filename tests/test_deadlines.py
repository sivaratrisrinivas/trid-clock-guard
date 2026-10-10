"""Deterministic tests for the TRID date math. No LLM, no network.

Dates are checked against the examples in the official commentary where one
exists (comments 19(e)(1)(iii)-1, 19(e)(1)(iii)-2, 19(e)(1)(iv)-2) and against
a 2026-2027 calendar otherwise.
"""
from datetime import date, datetime, timezone

from app.calendars import FRI, MON, SAT, THU, TUE, WED, GeneralCalendar
from app.rules import deemed_receipt_date, earliest_consummation_date, le_due_date, local_date

MON_FRI = GeneralCalendar(open_weekdays=frozenset({MON, TUE, WED, THU, FRI}))
MON_SAT = GeneralCalendar(open_weekdays=frozenset({MON, TUE, WED, THU, FRI, SAT}))


def test_commentary_example_monday_application_due_thursday():
    # Comment 19(e)(1)(iii)-1: received Monday -> deliver or mail by Thursday.
    assert le_due_date(date(2015, 6, 1), MON_FRI) == date(2015, 6, 4)


def test_saturday_open_lender_counts_saturday_and_skips_columbus_day():
    # Fri 9 Oct 2026 -> Sat 10 (1), Mon 12 Columbus Day closed, Tue 13 (2), Wed 14 (3).
    assert le_due_date(date(2026, 10, 9), MON_SAT) == date(2026, 10, 14)


def test_saturday_closed_lender_moves_due_date_to_thursday():
    # Same application, lender closed Saturdays: Tue 13, Wed 14, Thu 15.
    assert le_due_date(date(2026, 10, 9), MON_FRI) == date(2026, 10, 15)


def test_lender_open_on_columbus_day_counts_it():
    # General definition follows the lender's actual office days, not the federal list.
    open_on_holidays = GeneralCalendar(closes_on_federal_holidays=False)
    assert le_due_date(date(2026, 10, 9), open_on_holidays) == date(2026, 10, 14)


def test_general_rule_observed_friday_depends_on_lender():
    # 4 Jul 2026 is a Saturday, observed Fri 3 Jul. Application Wed 1 Jul.
    # Lender closed on the observed day: Thu 2 (1), Mon 6 (2), Tue 7 (3).
    assert le_due_date(date(2026, 7, 1), MON_FRI) == date(2026, 7, 7)
    # Lender open on the observed Friday: Thu 2, Fri 3, Mon 6.
    open_observed = GeneralCalendar(closes_on_observed_day=False)
    assert le_due_date(date(2026, 7, 1), open_observed) == date(2026, 7, 6)


def test_specific_rule_observed_friday_is_a_business_day():
    # Comment 2(a)(6)-2: under the specific definition the observed Friday counts.
    # LE mailed Wed 1 Jul 2026: Thu 2 (1), Fri 3 (2), Sat 4 holiday, Sun, Mon 6 (3).
    assert deemed_receipt_date(date(2026, 7, 1), "mail") == date(2026, 7, 6)
    # Juneteenth 2027 is Sat 19 Jun, observed Fri 18 Jun. Mailed Thu 17 Jun:
    # Fri 18 (1), Sat 19 holiday, Sun, Mon 21 (2), Tue 22 (3).
    assert deemed_receipt_date(date(2027, 6, 17), "mail") == date(2027, 6, 22)


def test_mailbox_rule_email_counts_saturday_skips_sunday_and_holiday():
    # Comment 19(e)(1)(iv)-2: emailed Monday -> considered received Thursday.
    assert deemed_receipt_date(date(2015, 6, 1), "email") == date(2015, 6, 4)
    # Emailed Sat 10 Oct 2026: Sun no, Mon 12 Columbus Day no, Tue 13, Wed 14, Thu 15.
    assert deemed_receipt_date(date(2026, 10, 10), "email") == date(2026, 10, 15)
    # In person: received the same day.
    assert deemed_receipt_date(date(2026, 10, 10), "in_person") == date(2026, 10, 10)


def test_seven_business_day_waiting_period():
    # Comment 19(e)(1)(iii)-2: mailed Mon June 1 -> consummation on or after Tue June 9.
    assert earliest_consummation_date(date(2015, 6, 1)) == date(2015, 6, 9)
    # Demo file: LE emailed Sat 10 Oct 2026 -> Tue 13 .. Sat 17 (5), Mon 19 (6), Tue 20 (7).
    assert earliest_consummation_date(date(2026, 10, 10)) == date(2026, 10, 20)


def test_thanksgiving_and_christmas_week():
    # Wed 25 Nov 2026: Thu 26 Thanksgiving, Fri 27 (1), Mon 30 (2), Tue 1 Dec (3).
    assert le_due_date(date(2026, 11, 25), MON_FRI) == date(2026, 12, 1)
    # Thu 24 Dec 2026: Fri 25 Christmas, Mon 28 (1), Tue 29 (2), Wed 30 (3).
    assert le_due_date(date(2026, 12, 24), MON_FRI) == date(2026, 12, 30)


def test_after_hours_and_weekend_receipt_use_lender_local_date():
    # 11:30 PM Pacific on Fri 9 Oct is already Sat 10 Oct in UTC.
    # The receipt date is read in the lender's zone, so it stays Friday.
    ts = datetime(2026, 10, 10, 6, 30, tzinfo=timezone.utc)
    received = local_date(ts, "America/Los_Angeles")
    assert received == date(2026, 10, 9)
    assert le_due_date(received, MON_SAT) == date(2026, 10, 14)
    # Received on a Sunday at a Mon-Fri lender: counting starts after Sunday,
    # Mon 12 is Columbus Day, so Tue 13, Wed 14, Thu 15.
    assert le_due_date(date(2026, 10, 11), MON_FRI) == date(2026, 10, 15)
