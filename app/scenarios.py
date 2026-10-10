"""Three synthetic borrower conversations. Every name, number, and address is
made up. Penny's turns are scripted; the guard only reads them."""

PDT = "-07:00"


def _t(day: str, hm: str, off: str = PDT) -> str:
    return f"{day}T{hm}:00{off}"


def P(ts, text, asks=None):
    return {"kind": "message", "role": "penny", "ts": ts, "text": text, "asks": asks}


def B(ts, text):
    return {"kind": "message", "role": "borrower", "ts": ts, "text": text}


def FEE(ts, fee_type, amount):
    return {"kind": "tool", "ts": ts, "tool": "charge_fee", "args": {"fee_type": fee_type, "amount": amount}}


D9, D10, D11, D13, D16 = "2026-10-09", "2026-10-10", "2026-10-11", "2026-10-13", "2026-10-16"

SCENARIOS = {
    "maya": {
        "title": "Maya: purchase, 6th item lands Friday before Columbus Day",
        "tenant": "harbor_point",
        "steps": [
            P(_t(D9, "14:02"), "Hi, I'm Penny, the digital assistant for Harbor Point Home Loans. Who am I speaking with?", "name"),
            B(_t(D9, "14:03"), "Maya Ortiz-Chen"),
            P(_t(D9, "14:03"), "Nice to meet you, Maya. What's your household income?", "income"),
            B(_t(D9, "14:05"), "I make about $142,000 a year as a nurse."),
            P(_t(D9, "14:06"), "Great. Have you found a home yet?", "property_address"),
            B(_t(D9, "14:08"), "Yes! 1418 Alder Creek Rd, Sacramento, CA 95822"),
            P(_t(D9, "14:08"), "Love it. What do you think the home is worth?", "property_value"),
            B(_t(D9, "14:09"), "We think it's worth about six and a half."),
            P(_t(D9, "14:10"), "And how much are you hoping to borrow?", "loan_amount"),
            B(_t(D9, "14:11"), "Around $520,000."),
            P(_t(D9, "16:46"), "To check your credit I'll need your Social Security number.", "ssn"),
            B(_t(D9, "16:47"), "Sure, it's 512-55-0198."),
            FEE(_t(D9, "16:48"), "appraisal", 650),
            FEE(_t(D9, "16:48"), "credit_report", 35),
            {"kind": "le_send", "ts": _t(D10, "10:00"), "method": "email"},
            FEE(_t(D10, "10:05"), "appraisal", 650),
            FEE(_t(D16, "09:00"), "appraisal", 650),
            B(_t(D16, "11:20"), "I reviewed the Loan Estimate. Yes, let's proceed."),
            FEE(_t(D16, "11:22"), "appraisal", 650),
        ],
    },
    "daniel": {
        "title": "Daniel: ITIN instead of SSN, Sunday application, later amended, then withdrawn",
        "tenant": "ridgeline",
        "steps": [
            P(_t(D11, "10:15"), "Hi, I'm Penny for Ridgeline Community Bank. What's your name?", "name"),
            B(_t(D11, "10:16"), "Hi, I'm Daniel Reyes and I'm looking to buy a condo."),
            P(_t(D11, "10:16"), "Thanks Daniel. What's the address?", "property_address"),
            B(_t(D11, "10:18"), "220 Harbor View Way, Unit 4B, San Diego, CA 92101"),
            P(_t(D11, "10:18"), "What's your income?", "income"),
            B(_t(D11, "10:20"), "around 9,500 a month"),
            P(_t(D11, "10:21"), "What's the condo worth, and how much would you borrow?", "property_value"),
            B(_t(D11, "10:23"), "Listed at 615 but we'd borrow 480k"),
            P(_t(D11, "10:24"), "I'll need an SSN, or the ID you use for credit, to pull credit.", "ssn"),
            B(_t(D11, "10:26"), "I don't have an SSN. My ITIN is 912-78-3456."),
            {"kind": "tool", "ts": _t(D11, "10:27"), "tool": "collect_payment_method", "args": {"purpose": "hold for processing fee"}},
            B(_t(D13, "09:40"), "Actually, can we make the loan amount $500,000?"),
            B(_t(D13, "15:05"), "I'm going with another lender, please withdraw my application."),
            FEE(_t(D13, "15:06"), "application", 400),
        ],
    },
    "priya": {
        "title": "Priya: five of six items, SSN promised tomorrow, no application yet",
        "tenant": "harbor_point",
        "steps": [
            P(_t(D9, "11:00"), "Hi, I'm Penny. Who am I speaking with?", "name"),
            B(_t(D9, "11:01"), "Priya Natarajan"),
            P(_t(D9, "11:01"), "What's your annual income?", "income"),
            B(_t(D9, "11:02"), "We earn $188,000 per year combined."),
            P(_t(D9, "11:03"), "What's the property address and what do you think it's worth?", "property_address"),
            B(_t(D9, "11:05"), "77 Juniper Ln, Davis, CA 95616. We'd estimate it's worth $735,000."),
            P(_t(D9, "11:05"), "How much would you like to borrow?", "loan_amount"),
            B(_t(D9, "11:06"), "We want to borrow $588,000."),
            P(_t(D9, "11:07"), "Last thing: your SSN for the credit check.", "ssn"),
            B(_t(D9, "11:08"), "I'll send my SSN tomorrow, need to find my card."),
            FEE(_t(D9, "11:09"), "application", 400),
        ],
    },
}
