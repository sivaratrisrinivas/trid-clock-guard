"""Two fictional lenders. Office days are tenant config because the general
business-day definition in 1026.2(a)(6) depends on when each creditor's
offices are open."""
from .calendars import FRI, MON, SAT, THU, TUE, WED, GeneralCalendar

TENANTS = {
    "harbor_point": {
        "id": "harbor_point",
        "name": "Harbor Point Home Loans",
        "note": "fictional lender, offices open Mon to Sat, closed on federal holidays",
        "tz": "America/Los_Angeles",
        "calendar": GeneralCalendar(open_weekdays=frozenset({MON, TUE, WED, THU, FRI, SAT})),
    },
    "ridgeline": {
        "id": "ridgeline",
        "name": "Ridgeline Community Bank",
        "note": "fictional lender, offices open Mon to Fri, closed on federal holidays",
        "tz": "America/Los_Angeles",
        "calendar": GeneralCalendar(open_weekdays=frozenset({MON, TUE, WED, THU, FRI})),
    },
}
