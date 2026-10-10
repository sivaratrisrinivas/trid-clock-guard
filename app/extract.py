"""Pull the six Reg Z application items (12 CFR 1026.2(a)(3)(ii)) out of
borrower chat turns. Rules first. An optional free-tier LLM pass only runs
when USE_LLM=1 and a key is present, and only for a turn where the rules found
nothing for the item Penny just asked about. The demo never needs it."""
from __future__ import annotations

import json
import os
import re
import urllib.request

ITEMS = ["name", "income", "ssn", "property_address", "property_value", "loan_amount"]
LABELS = {
    "name": "Consumer's name",
    "income": "Consumer's income",
    "ssn": "SSN (to obtain a credit report)",
    "property_address": "Property address",
    "property_value": "Estimated property value",
    "loan_amount": "Mortgage loan amount sought",
}

WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
           "eight": 8, "nine": 9, "ten": 10}

SSN_RE = re.compile(r"\b(\d{3})[- ]?(\d{2})[- ]?(\d{4})\b")
NAME_RE = re.compile(r"(?i:my name is|i'm|i am|this is|name's|it's)\s+([A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+){1,3})")
ADDR_RE = re.compile(
    r"\b\d{2,6}\s+(?:[A-Z][a-zA-Z]*\s+){1,4}(?:St|Street|Rd|Road|Ave|Avenue|Blvd|Ln|Lane|Dr|Drive|Ct|Court|Way|Pl|Place|Ter|Terrace|Cir|Circle)\b\.?"
    r"(?:,?\s*(?:Apt|Unit|#)\s*\w+)?(?:,\s*[A-Z][a-zA-Z .]+)?(?:,\s*[A-Z]{2})?(?:\s+\d{5})?")
MONEY_RE = re.compile(
    r"(\$)?\s?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(k|K|thousand|m|M|million)?\b"
    r"|\b(" + "|".join(WORDNUM) + r"|\d+)\s+and\s+a\s+half\b", re.I)

KEYWORDS = {
    "income": re.compile(r"\b(make|earn|income|salary|a year|per year|annually|/yr|a month|per month)\b", re.I),
    "property_value": re.compile(r"\b(worth|value|valued|apprais\w*|estimate|listed|list price)\b", re.I),
    "loan_amount": re.compile(r"\b(borrow|loan amount|loan of|finance|financing|mortgage of)\b", re.I),
}


def _amounts(text: str):
    out = []
    for m in MONEY_RE.finditer(text):
        if m.group(4):
            base = WORDNUM.get(m.group(4).lower()) or float(m.group(4))
            out.append((float(base) + 0.5, m.group(0), False, True, m.start()))
            continue
        dollar, num, suf = m.group(1), m.group(2), m.group(3)
        if SSN_RE.search(text[max(0, m.start() - 4): m.end() + 8]) and not dollar:
            continue
        v = float(num.replace(",", ""))
        if suf and suf.lower() in ("k", "thousand"):
            v *= 1_000
        elif suf and suf.lower() in ("m", "million"):
            v *= 1_000_000
        out.append((v, m.group(0).strip(), bool(dollar), bool(suf), m.start()))
    return out


def _normalize(item: str, v: float, raw: str, explicit: bool):
    """Scale shorthand like '6 and a half' or '615' to dollars."""
    note = None
    if item in ("property_value", "loan_amount") and v < 10_000:
        scale = 100_000 if v < 100 else 1_000
        note = f"read '{raw}' as ${v * scale:,.0f} (shorthand)"
        v *= scale
    elif item == "income" and v < 1_000 and not explicit:
        note = f"read '{raw}' as ${v * 1000:,.0f} a year (shorthand)"
        v *= 1_000
    return v, note


def _fmt_income(text: str, v: float) -> str:
    if re.search(r"\b(a month|per month|monthly|/mo)\b", text, re.I):
        return f"${v:,.0f}/month"
    return f"${v:,.0f}/year"


def extract(text: str, asked: str | None = None) -> list[dict]:
    """Return found items: {item, value, quote, method, note}."""
    found: dict[str, dict] = {}

    m = SSN_RE.search(text)
    if m and (asked == "ssn" or re.search(r"\b(ssn|social|itin|tax id)\b", text, re.I) or "-" in m.group(0)):
        area = m.group(1)
        kind = "ITIN (substitute identifier, comment 2(a)(3)-2)" if area.startswith("9") else "SSN"
        found["ssn"] = {"item": "ssn", "value": f"{kind} ***-**-{m.group(3)}", "quote": "***-**-" + m.group(3),
                        "method": "rules", "note": "stored masked; full number never persisted"}

    m = ADDR_RE.search(text)
    if m:
        found["property_address"] = {"item": "property_address", "value": m.group(0).strip(" ."),
                                     "quote": m.group(0).strip(" ."), "method": "rules", "note": None}

    m = NAME_RE.search(text)
    if m and "property_address" not in found:
        found["name"] = {"item": "name", "value": m.group(1), "quote": m.group(0), "method": "rules", "note": None}
    elif asked == "name" and re.fullmatch(r"\s*([A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+){1,3})\.?\s*", text):
        n = text.strip(" .")
        found["name"] = {"item": "name", "value": n, "quote": n, "method": "rules", "note": None}

    amts = _amounts(text)
    cands = []
    for i, (v, raw, dollar, suf, pos) in enumerate(amts):
        for k, rx in KEYWORDS.items():
            for km in rx.finditer(text):
                # prefer a keyword just before the number ("borrow 480k")
                d = pos - km.end() if km.end() <= pos else (km.start() - pos) + 25
                if d < 60:
                    cands.append((d, k, i))
    if not cands and len(amts) == 1 and asked in ("income", "property_value", "loan_amount"):
        cands.append((0, asked, 0))
    used = set()
    for d, item, i in sorted(cands):
        if item in found or i in used:
            continue
        used.add(i)
        v, raw, dollar, suf, pos = amts[i]
        v2, note = _normalize(item, v, raw, dollar or suf)
        val = _fmt_income(text, v2) if item == "income" else f"${v2:,.0f}"
        found[item] = {"item": item, "value": val, "quote": raw, "method": "rules", "note": note}

    if asked and asked not in found and os.environ.get("USE_LLM") == "1":
        llm = _llm_extract(text, asked)
        if llm:
            found[asked] = llm
    return list(found.values())


INTENT_RE = re.compile(
    r"\b(i(?:'d| would)? (?:like|want) to (?:proceed|move forward|go ahead)|let'?s (?:proceed|go ahead|move forward)"
    r"|please proceed|yes,? (?:let'?s )?(?:proceed|go ahead|move forward)|i intend to proceed)\b", re.I)
RECEIPT_RE = re.compile(r"\b(got|received|have|reviewed|read|looked over)\b.{0,30}\b(loan estimate|LE)\b", re.I)
WITHDRAW_RE = re.compile(r"\b(withdraw|going with another lender|cancel my application|no longer want)\b", re.I)


def _llm_extract(text: str, item: str) -> dict | None:
    """Free-tier LLM normalizer (Groq via GROQ_API_KEY, else Gemini key file).
    Returns None on any failure; the caller keeps the rules result."""
    prompt = (f"Borrower message: {text!r}\nExtract only the field '{item}' ({LABELS[item]}). "
              'Reply with JSON {"value": "...", "quote": "exact words used"} or {"value": null}.')
    try:
        if os.environ.get("GROQ_API_KEY"):
            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/chat/completions",
                data=json.dumps({"model": "llama-3.1-8b-instant", "temperature": 0,
                                 "response_format": {"type": "json_object"},
                                 "messages": [{"role": "user", "content": prompt}]}).encode(),
                headers={"Authorization": "Bearer " + os.environ["GROQ_API_KEY"], "Content-Type": "application/json"})
            out = json.loads(urllib.request.urlopen(req, timeout=10).read())["choices"][0]["message"]["content"]
        else:
            path = os.environ.get("GEMINI_KEY_FILE", "/workspace/.secrets/gemini_key")
            key = os.environ.get("GEMINI_API_KEY") or (open(path).read().strip() if os.path.exists(path) else None)
            if not key:
                return None
            req = urllib.request.Request(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
                data=json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                                 "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}).encode(),
                headers={"x-goog-api-key": key, "Content-Type": "application/json"})
            out = json.loads(urllib.request.urlopen(req, timeout=10).read())["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(out)
        if data.get("value"):
            return {"item": item, "value": str(data["value"]), "quote": data.get("quote") or text,
                    "method": "llm", "note": "normalized by free-tier LLM"}
    except Exception:
        return None
    return None


def mask_ids(text: str) -> str:
    """Mask anything shaped like an SSN/ITIN before the message is stored."""
    return SSN_RE.sub(lambda m: "***-**-" + m.group(3), text)
