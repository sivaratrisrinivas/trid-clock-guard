from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import guard
from .db import BACKEND, LoanFile, SessionLocal, init_db
from .scenarios import SCENARIOS
from .tenants import TENANTS

app = FastAPI(title="TRID Clock Guard", version="0.1.0")
STATIC = Path(__file__).resolve().parent.parent / "static"
init_db()


class NewFile(BaseModel):
    scenario: str | None = "maya"
    tenant: str | None = None
    play_until: int | None = None  # replay the first N scripted steps


class Event(BaseModel):
    kind: str
    ts: str
    role: str | None = None
    text: str | None = None
    asks: str | None = None
    method: str | None = None
    tool: str | None = None
    args: dict | None = None


class TenantSwitch(BaseModel):
    tenant: str


def _get(s, fid):
    f = s.get(LoanFile, fid)
    if not f:
        raise HTTPException(404, "no such file")
    return f


@app.get("/api/health")
def health():
    return {"ok": True, "db": BACKEND}


@app.get("/api/scenarios")
def scenarios():
    return {k: {"title": v["title"], "tenant": v["tenant"], "steps": v["steps"]} for k, v in SCENARIOS.items()}


@app.get("/api/tenants")
def tenants():
    return [{k: v for k, v in t.items() if k != "calendar"} for t in TENANTS.values()]


@app.post("/api/files")
def new_file(body: NewFile):
    sc = SCENARIOS.get(body.scenario) if body.scenario else None
    tenant = body.tenant or (sc["tenant"] if sc else "harbor_point")
    if tenant not in TENANTS:
        raise HTTPException(400, "unknown tenant")
    with SessionLocal() as s:
        f = guard.create_file(s, tenant, body.scenario)
        for step in (sc["steps"][: body.play_until] if sc and body.play_until else []):
            guard.add_event(s, f, step)
        return guard.state(s, f)


@app.get("/api/files/{fid}")
def get_file(fid: str):
    with SessionLocal() as s:
        return guard.state(s, _get(s, fid))


@app.post("/api/files/{fid}/events")
def post_event(fid: str, ev: Event):
    with SessionLocal() as s:
        f = _get(s, fid)
        try:
            result = guard.add_event(s, f, ev.model_dump(exclude_none=True))
        except (ValueError, KeyError) as e:
            raise HTTPException(400, str(e))
        return {"result": result, "state": guard.state(s, f)}


@app.put("/api/files/{fid}/tenant")
def switch_tenant(fid: str, body: TenantSwitch):
    if body.tenant not in TENANTS:
        raise HTTPException(400, "unknown tenant")
    with SessionLocal() as s:
        f = _get(s, fid)
        f.tenant = body.tenant
        s.commit()
        return guard.state(s, f)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
