"""The guard: item tracking, the application trigger, the LE clock, and the
fee-tool gate. All state lives in Postgres (or the SQLite fallback)."""
from __future__ import annotations

import secrets
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from .calendars import business_days_after
from .db import AppItem, Clock, IntakeEvent, LoanFile, ToolCallAudit
from .extract import INTENT_RE, ITEMS, LABELS, RECEIPT_RE, WITHDRAW_RE, extract, mask_ids
from .rules import SPECIFIC, deemed_receipt_date, earliest_consummation_date, le_due_date, local_date
from .tenants import TENANTS

FEE_TOOLS = {"charge_fee", "collect_payment_method"}


def parse(ts: str) -> datetime:
    d = datetime.fromisoformat(ts)
    if d.tzinfo is None:
        raise ValueError("timestamp needs a UTC offset")
    return d


def fmt_dt(ts: str | None, tz: str) -> str | None:
    if not ts:
        return None
    d = parse(ts).astimezone(ZoneInfo(tz))
    return d.strftime("%a %b %-d, %-I:%M %p") + " PT"


def fmt_d(d: date | None) -> str | None:
    return d.strftime("%a %b %-d, %Y") if d else None


def create_file(s: Session, tenant: str, scenario: str | None) -> LoanFile:
    f = LoanFile(id=secrets.token_hex(4), tenant=tenant, scenario=scenario,
                 created_at=datetime.now(timezone.utc).isoformat())
    s.add(f)
    s.flush()
    s.add(Clock(file_id=f.id))
    s.commit()
    return f


def _items(s: Session, fid: str) -> dict[str, AppItem]:
    rows = s.scalars(select(AppItem).where(AppItem.file_id == fid, AppItem.superseded.is_(False))).all()
    return {r.item: r for r in rows}


def _last_ask(s: Session, fid: str) -> str | None:
    ev = s.scalars(select(IntakeEvent).where(IntakeEvent.file_id == fid, IntakeEvent.kind == "message",
                                            IntakeEvent.role == "penny").order_by(IntakeEvent.id.desc())).first()
    return (ev.meta or {}).get("asks") if ev else None


def _received_at(c: Clock, tz: str, at: datetime) -> bool:
    """Has the consumer received the LE as of `at`?"""
    if not c.le_sent_at:
        return False
    if c.receipt_evidence_at and parse(c.receipt_evidence_at) <= at:
        return True
    deemed = deemed_receipt_date(local_date(parse(c.le_sent_at), tz), c.le_method)
    return local_date(at, tz) >= deemed


def _sys(s, fid, ts, text):
    s.add(IntakeEvent(file_id=fid, ts=ts, kind="system", role="guard", text=text))


def add_event(s: Session, f: LoanFile, body: dict) -> dict:
    tenant = TENANTS[f.tenant]
    tz = tenant["tz"]
    ts = body["ts"]
    at = parse(ts)
    c = s.get(Clock, f.id)
    if not f.sim_now or parse(f.sim_now) < at:
        f.sim_now = ts
    kind = body["kind"]
    result: dict = {"kind": kind}

    if kind == "message":
        role = body.get("role", "borrower")
        asked = _last_ask(s, f.id) if role == "borrower" else None
        ev = IntakeEvent(file_id=f.id, ts=ts, kind="message", role=role, text=mask_ids(body["text"]),
                         meta={"asks": body.get("asks")} if role == "penny" else None)
        s.add(ev)
        s.flush()
        if role == "borrower":
            have = _items(s, f.id)
            new = []
            for it in extract(body["text"], asked):
                old = have.get(it["item"])
                if old and old.value == it["value"]:
                    continue
                if old:
                    old.superseded = True
                    if c.application_received_at:
                        _sys(s, f.id, ts, f"{LABELS[it['item']]} amended to {it['value']}. Application date stays "
                             f"{fmt_dt(c.application_received_at, tz)}; the trigger is the first time all six were on file.")
                s.add(AppItem(file_id=f.id, item=it["item"], value=it["value"], quote=it["quote"],
                              source_event_id=ev.id, captured_at=ts, method=it["method"], note=it["note"]))
                new.append(it["item"])
            s.flush()
            result["captured"] = new
            if not c.application_received_at and len(_items(s, f.id)) == 6:
                c.application_received_at = ts
                c.trigger_event_id = ev.id
                due = le_due_date(local_date(at, tz), tenant["calendar"])
                _sys(s, f.id, ts, f"6th Reg Z item captured. Application received {fmt_dt(ts, tz)}. "
                     f"Loan Estimate must be delivered or mailed by {fmt_d(due)}.")
                result["application_received"] = True
            if c.le_sent_at and not c.receipt_evidence_at and RECEIPT_RE.search(body["text"]) and not _received_at(c, tz, at):
                c.receipt_evidence_at, c.receipt_evidence_event_id = ts, ev.id
                _sys(s, f.id, ts, "Borrower confirmed receiving the LE. Logged as evidence of earlier receipt (comment 19(e)(1)(iv)-2).")
            if INTENT_RE.search(body["text"]) and not c.intent_at:
                if c.le_sent_at and _received_at(c, tz, at):
                    c.intent_at, c.intent_event_id, c.intent_quote = ts, ev.id, body["text"]
                    _sys(s, f.id, ts, "Intent to proceed documented after LE receipt (1026.19(e)(2)(i)(A); comment 19(e)(2)(i)(A)-2).")
                    result["intent"] = True
                else:
                    _sys(s, f.id, ts, "Borrower said to proceed, but the LE is not yet received. Not counted as intent.")
            if WITHDRAW_RE.search(body["text"]) and not c.withdrawn_at:
                c.withdrawn_at = ts
                _sys(s, f.id, ts, "Borrower withdrew. LE clock stopped (comment 19(e)(1)(iii)-3).")

    elif kind == "le_send":
        method = body.get("method", "email")
        if method not in ("in_person", "mail", "email"):
            raise ValueError("method must be in_person, mail or email")
        c.le_sent_at, c.le_method = ts, method
        s.add(IntakeEvent(file_id=f.id, ts=ts, kind="le_send", role="penny",
                          text=f"Loan Estimate sent ({method.replace('_', ' ')}).", meta={"method": method}))
        d = local_date(at, tz)
        _sys(s, f.id, ts, f"LE sent by {method.replace('_', ' ')}. Considered received {fmt_d(deemed_receipt_date(d, method))}; "
             f"earliest consummation {fmt_d(earliest_consummation_date(d))}.")

    elif kind == "intent":  # LO logs intent given by phone, email, signed form
        if not _received_at(c, tz, at):
            raise ValueError("Intent can only be logged after the consumer has received the LE")
        ev = IntakeEvent(file_id=f.id, ts=ts, kind="message", role="lo", text=body.get("text", "Intent to proceed logged by LO"))
        s.add(ev)
        s.flush()
        c.intent_at, c.intent_event_id, c.intent_quote = ts, ev.id, ev.text

    elif kind == "tool":
        decision, reason, cite = gate(c, tenant, body["tool"], body.get("args") or {}, at)
        s.add(ToolCallAudit(file_id=f.id, ts=ts, tool=body["tool"], args=body.get("args") or {},
                            decision=decision, reason=reason, cite=cite))
        result.update(decision=decision, reason=reason, cite=cite)

    elif kind == "advance":
        pass
    else:
        raise ValueError("unknown kind")
    s.commit()
    return result


def gate(c: Clock, tenant: dict, tool: str, args: dict, at: datetime) -> tuple[str, str, str]:
    tz = tenant["tz"]
    if tool not in FEE_TOOLS:
        return "allowed", "Not a fee-taking tool.", "-"
    fee = args.get("fee_type", "payment method")
    if tool == "charge_fee" and fee == "credit_report":
        return "allowed", "Credit report fee is the one fee allowed before the LE.", "1026.19(e)(2)(i)(B)"
    what = f"{fee} fee" if tool == "charge_fee" else "Collecting a card or check counts as imposing a fee"
    cite = "1026.19(e)(2)(i)(A)" + ("; comment 19(e)(2)(i)(A)-5" if tool == "collect_payment_method" else "")
    if c.withdrawn_at:
        return "blocked", f"{what}: file withdrawn {fmt_dt(c.withdrawn_at, tz)}.", cite
    if not c.application_received_at:
        return "blocked", f"{what}: no Loan Estimate yet. Only a credit report fee may be charged before the borrower receives the LE and says to proceed.", cite
    if not c.le_sent_at:
        due = le_due_date(local_date(parse(c.application_received_at), tz), tenant["calendar"])
        return "blocked", f"{what}: application received {fmt_dt(c.application_received_at, tz)}, LE not delivered yet (due {fmt_d(due)}).", cite
    if not _received_at(c, tz, at):
        deemed = deemed_receipt_date(local_date(parse(c.le_sent_at), tz), c.le_method)
        return ("blocked", f"{what}: LE {c.le_method}ed {fmt_dt(c.le_sent_at, tz)}, considered received {fmt_d(deemed)} "
                "under the mailbox rule. No earlier receipt on file.", cite + "; 1026.19(e)(1)(iv)")
    if not c.intent_at or parse(c.intent_at) > at:
        return ("blocked", f"{what}: LE received, but no documented intent to proceed. Silence is not intent.",
                cite + "; comment 19(e)(2)(i)(A)-2")
    return "allowed", f"LE received and intent to proceed documented {fmt_dt(c.intent_at, tz)}: \"{c.intent_quote}\"", cite


def _days(start: date, n: int, cal):
    return [{"date": d.isoformat(), "label": d.strftime("%a %b %-d"), "skipped": r} for d, r in business_days_after(start, n, cal)]


def state(s: Session, f: LoanFile) -> dict:
    tenant = TENANTS[f.tenant]
    tz, cal = tenant["tz"], tenant["calendar"]
    c = s.get(Clock, f.id)
    events = s.scalars(select(IntakeEvent).where(IntakeEvent.file_id == f.id).order_by(IntakeEvent.id)).all()
    items = _items(s, f.id)
    all_items = s.scalars(select(AppItem).where(AppItem.file_id == f.id).order_by(AppItem.id)).all()
    audit = s.scalars(select(ToolCallAudit).where(ToolCallAudit.file_id == f.id).order_by(ToolCallAudit.id)).all()
    now = parse(f.sim_now) if f.sim_now else None
    clock: dict = {"application_received": bool(c.application_received_at)}
    if c.application_received_at:
        app_d = local_date(parse(c.application_received_at), tz)
        due = le_due_date(app_d, cal)
        clock.update(application_received_at=fmt_dt(c.application_received_at, tz), application_date=fmt_d(app_d),
                     trigger_event_id=c.trigger_event_id, le_due=fmt_d(due), le_due_short=due.strftime("%a %b %-d"),
                     le_due_days=_days(app_d, 3, cal), calendar=cal.name)
        if c.withdrawn_at:
            clock["status"] = "withdrawn"
        elif c.le_sent_at:
            sent_d = local_date(parse(c.le_sent_at), tz)
            clock["status"] = "le_sent_on_time" if sent_d <= due else "le_sent_late"
        elif now:
            nd = local_date(now, tz)
            clock["status"] = "overdue" if nd > due else ("due_today" if nd == due else "running")
    if c.le_sent_at:
        sent_d = local_date(parse(c.le_sent_at), tz)
        deemed = deemed_receipt_date(sent_d, c.le_method)
        clock.update(le_sent_at=fmt_dt(c.le_sent_at, tz), le_method=c.le_method, deemed_receipt=fmt_d(deemed),
                     deemed_days=_days(sent_d, 3, SPECIFIC) if c.le_method != "in_person" else [],
                     receipt_evidence_at=fmt_dt(c.receipt_evidence_at, tz),
                     earliest_consummation=fmt_d(earliest_consummation_date(sent_d)),
                     received_now=_received_at(c, tz, now) if now else False)
    clock.update(intent_at=fmt_dt(c.intent_at, tz), intent_quote=c.intent_quote, withdrawn_at=fmt_dt(c.withdrawn_at, tz))
    return {
        "id": f.id, "scenario": f.scenario,
        "tenant": {k: v for k, v in tenant.items() if k != "calendar"},
        "sim_now": fmt_dt(f.sim_now, tz),
        "items": [{"item": k, "label": LABELS[k], **({"value": items[k].value, "quote": items[k].quote,
                   "source_event_id": items[k].source_event_id, "captured_at": fmt_dt(items[k].captured_at, tz),
                   "method": items[k].method, "note": items[k].note} if k in items else {})} for k in ITEMS],
        "item_history": [{"item": r.item, "value": r.value, "superseded": r.superseded, "source_event_id": r.source_event_id,
                          "captured_at": fmt_dt(r.captured_at, tz)} for r in all_items],
        "count": len(items),
        "clock": clock,
        "events": [{"id": e.id, "ts": fmt_dt(e.ts, tz), "kind": e.kind, "role": e.role, "text": e.text} for e in events],
        "audit": [{"id": a.id, "ts": fmt_dt(a.ts, tz), "tool": a.tool, "args": a.args, "decision": a.decision,
                   "reason": a.reason, "cite": a.cite} for a in audit],
    }
