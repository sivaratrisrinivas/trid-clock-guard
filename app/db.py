"""Postgres when DATABASE_URL is set (Render free Postgres, local Postgres),
otherwise an embedded SQLite file so setup needs nothing."""
from __future__ import annotations

import os

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

url = os.environ.get("DATABASE_URL", "sqlite:///./trid_guard.db")
if url.startswith("postgres://"):
    url = "postgresql+psycopg://" + url[len("postgres://"):]
elif url.startswith("postgresql://"):
    url = "postgresql+psycopg://" + url[len("postgresql://"):]
engine = create_engine(url, pool_pre_ping=True, **({"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}))
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
BACKEND = "postgres" if url.startswith("postgresql") else "sqlite (embedded fallback)"


class Base(DeclarativeBase):
    pass


class LoanFile(Base):
    __tablename__ = "loan_file"
    id: Mapped[str] = mapped_column(String(12), primary_key=True)
    tenant: Mapped[str] = mapped_column(String(40))
    scenario: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    sim_now: Mapped[str | None] = mapped_column(String(40), nullable=True)


class IntakeEvent(Base):
    __tablename__ = "intake_event"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(ForeignKey("loan_file.id"), index=True)
    ts: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(20))  # message | le_send | tool | system
    role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)  # SSN-shaped strings masked before insert
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class AppItem(Base):
    __tablename__ = "app_item"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(ForeignKey("loan_file.id"), index=True)
    item: Mapped[str] = mapped_column(String(30))
    value: Mapped[str] = mapped_column(String(200))
    quote: Mapped[str] = mapped_column(String(300))
    source_event_id: Mapped[int] = mapped_column(ForeignKey("intake_event.id"))
    captured_at: Mapped[str] = mapped_column(String(40))
    method: Mapped[str] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    superseded: Mapped[bool] = mapped_column(Boolean, default=False)


class Clock(Base):
    __tablename__ = "clock"
    file_id: Mapped[str] = mapped_column(ForeignKey("loan_file.id"), primary_key=True)
    application_received_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    trigger_event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    le_sent_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    le_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    receipt_evidence_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    receipt_evidence_event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    intent_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    intent_event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    intent_quote: Mapped[str | None] = mapped_column(String(300), nullable=True)
    withdrawn_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class ToolCallAudit(Base):
    __tablename__ = "tool_call_audit"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(ForeignKey("loan_file.id"), index=True)
    ts: Mapped[str] = mapped_column(String(40))
    tool: Mapped[str] = mapped_column(String(40))
    args: Mapped[dict] = mapped_column(JSON)
    decision: Mapped[str] = mapped_column(String(10))  # allowed | blocked
    reason: Mapped[str] = mapped_column(Text)
    cite: Mapped[str] = mapped_column(String(200))


def init_db():
    Base.metadata.create_all(engine)
