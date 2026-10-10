"""Business-day calendars for Reg Z (12 CFR 1026).

Reg Z has two definitions of "business day" in 12 CFR 1026.2(a)(6):

* General: "a day on which the creditor's offices are open to the public for
  carrying on substantially all of its business functions." This one depends on
  the lender, so it is tenant config (which weekdays are open, which holidays
  close the office). Used for the Loan Estimate delivery deadline,
  1026.19(e)(1)(iii)(A). See comment 19(e)(1)(iii)-1.
* Specific: "all calendar days except Sundays and the legal public holidays
  specified in 5 U.S.C. 6103(a)". Used for the 7-business-day waiting period
  (1026.19(e)(1)(iii)(B)), the mailbox rule (1026.19(e)(1)(iv)) and others.
  Comment 2(a)(6)-2: when a fixed-date holiday falls on Saturday and is
  observed on Friday, the observed Friday IS a business day under this rule.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

MON, TUE, WED, THU, FRI, SAT, SUN = range(7)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    d = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def federal_holidays(year: int) -> dict[date, str]:
    """Legal public holidays listed in 5 U.S.C. 6103(a), on their actual dates.

    Juneteenth was added to 6103(a) on 17 June 2021. Inauguration Day is in
    6103(c), not 6103(a), so it is not included.
    """
    return {
        date(year, 1, 1): "New Year's Day",
        _nth_weekday(year, 1, MON, 3): "Birthday of Martin Luther King, Jr.",
        _nth_weekday(year, 2, MON, 3): "Washington's Birthday",
        _last_weekday(year, 5, MON): "Memorial Day",
        date(year, 6, 19): "Juneteenth National Independence Day",
        date(year, 7, 4): "Independence Day",
        _nth_weekday(year, 9, MON, 1): "Labor Day",
        _nth_weekday(year, 10, MON, 2): "Columbus Day",
        date(year, 11, 11): "Veterans Day",
        _nth_weekday(year, 11, THU, 4): "Thanksgiving Day",
        date(year, 12, 25): "Christmas Day",
    }


def observed_holidays(year: int) -> dict[date, str]:
    """Days federal offices close: a Saturday holiday moves to Friday, a Sunday
    holiday moves to Monday. Covers the Dec 31 case where next year's New
    Year's Day falls on a Saturday."""
    out: dict[date, str] = {}
    for y in (year, year + 1):
        for d, name in federal_holidays(y).items():
            if d.weekday() == SAT:
                d, name = d - timedelta(days=1), name + " (observed)"
            elif d.weekday() == SUN:
                d, name = d + timedelta(days=1), name + " (observed)"
            if d.year == year:
                out[d] = name
    return out


class Calendar:
    name = "calendar"

    def is_business_day(self, d: date) -> bool:  # pragma: no cover
        raise NotImplementedError

    def closed_reason(self, d: date) -> str | None:  # pragma: no cover
        raise NotImplementedError


class SpecificCalendar(Calendar):
    """1026.2(a)(6) specific definition: every day except Sundays and the
    actual 5 U.S.C. 6103(a) holiday dates. Saturdays count. Observed days
    (e.g. Fri 3 Jul 2026) count, per comment 2(a)(6)-2."""

    name = "specific (all days except Sundays and federal holidays)"

    def closed_reason(self, d: date) -> str | None:
        if d.weekday() == SUN:
            return "Sunday"
        return federal_holidays(d.year).get(d)

    def is_business_day(self, d: date) -> bool:
        return self.closed_reason(d) is None


@dataclass
class GeneralCalendar(Calendar):
    """1026.2(a)(6) general definition: days this creditor's offices are open
    for substantially all business functions. Tenant config."""

    open_weekdays: frozenset[int] = frozenset({MON, TUE, WED, THU, FRI})
    closes_on_federal_holidays: bool = True
    # Closed on the actual holiday date always (when the flag above is on).
    # Also closed on the shifted Friday/Monday when a holiday lands on a weekend?
    closes_on_observed_day: bool = True
    extra_closed: dict[date, str] = field(default_factory=dict)
    name: str = "general (days this lender's offices are open)"

    def closed_reason(self, d: date) -> str | None:
        if d in self.extra_closed:
            return self.extra_closed[d]
        if self.closes_on_federal_holidays:
            actual = federal_holidays(d.year)
            if d in actual:
                return actual[d]
            if self.closes_on_observed_day:
                obs = observed_holidays(d.year)
                if d in obs:
                    return obs[d]
        if d.weekday() not in self.open_weekdays:
            return "office closed (" + d.strftime("%A") + ")"
        return None

    def is_business_day(self, d: date) -> bool:
        return self.closed_reason(d) is None


def add_business_days(start: date, n: int, cal: Calendar) -> date:
    """The nth business day AFTER `start` (start itself is never counted,
    and start does not have to be a business day)."""
    d, count = start, 0
    while count < n:
        d += timedelta(days=1)
        if cal.is_business_day(d):
            count += 1
    return d


def business_days_after(start: date, n: int, cal: Calendar) -> list[tuple[date, str | None]]:
    """Every calendar day from start+1 through the nth business day, with the
    reason a day was skipped (None means it counted). Used to show the work."""
    out, d, count = [], start, 0
    while count < n:
        d += timedelta(days=1)
        r = cal.closed_reason(d)
        out.append((d, r))
        if r is None:
            count += 1
    return out
