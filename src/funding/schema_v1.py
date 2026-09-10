# Frozen schema for migration 0001. Never edit after release.
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Unicode,
    UnicodeText,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(Unicode(300))
    url: Mapped[str] = mapped_column(Unicode(2048))
    adapter: Mapped[str] = mapped_column(String(40))
    category: Mapped[str] = mapped_column(Unicode(100))
    coverage: Mapped[str] = mapped_column(UnicodeText)
    owner: Mapped[str] = mapped_column(Unicode(200))
    enabled: Mapped[bool] = mapped_column(Boolean)
    config_json: Mapped[str] = mapped_column(UnicodeText)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime)
    health: Mapped[str] = mapped_column(String(30), default="not_run")
    last_error: Mapped[str | None] = mapped_column(UnicodeText)


class Run(Base):
    __tablename__ = "collection_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(30), default="running")
    seen: Mapped[int] = mapped_column(Integer, default=0)
    changed: Mapped[int] = mapped_column(Integer, default=0)
    rejected: Mapped[int] = mapped_column(Integer, default=0)
    expected: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str | None] = mapped_column(UnicodeText)


class Opportunity(Base):
    __tablename__ = "opportunities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    external_id: Mapped[str] = mapped_column(Unicode(400))
    canonical_url: Mapped[str] = mapped_column(Unicode(2048))
    title: Mapped[str] = mapped_column(Unicode(1000))
    description: Mapped[str] = mapped_column(UnicodeText)
    funder: Mapped[str] = mapped_column(Unicode(500), index=True)
    programme: Mapped[str] = mapped_column(Unicode(200), index=True)
    instrument: Mapped[str] = mapped_column(String(40), index=True)
    language: Mapped[str] = mapped_column(String(10))
    source_status: Mapped[str] = mapped_column(String(30))
    opens_on: Mapped[date | None] = mapped_column(Date)
    deadline_on: Mapped[date | None] = mapped_column(Date, index=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime)
    deadline_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    deadline_model: Mapped[str] = mapped_column(String(40))
    total_budget: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    grant_max: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    funding_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    eligibility_text: Mapped[str] = mapped_column(UnicodeText)
    geographic_scope: Mapped[str] = mapped_column(String(30), index=True)
    detail_level: Mapped[str] = mapped_column(String(30))
    quality_flags_json: Mapped[str] = mapped_column(UnicodeText)
    content_hash: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class SourceItem(Base):
    __tablename__ = "source_items"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    external_id: Mapped[str] = mapped_column(Unicode(400))
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), index=True)
    raw_json: Mapped[str] = mapped_column(UnicodeText)
    raw_hash: Mapped[str] = mapped_column(String(64))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime)


class Tag(Base):
    __tablename__ = "opportunity_tags"
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(30), primary_key=True)
    value: Mapped[str] = mapped_column(Unicode(200), primary_key=True)
    basis: Mapped[str] = mapped_column(String(30))
    __table_args__ = (Index("ix_tag_lookup", "kind", "value"),)


class Deadline(Base):
    __tablename__ = "deadlines"
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), primary_key=True)
    stage: Mapped[int] = mapped_column(Integer, primary_key=True)
    due_on: Mapped[date] = mapped_column(Date, index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime)
    original: Mapped[str] = mapped_column(Unicode(100))
    timezone: Mapped[str] = mapped_column(String(60))


class Change(Base):
    __tablename__ = "changes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[str | None] = mapped_column(ForeignKey("opportunities.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    kind: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    payload_json: Mapped[str] = mapped_column(UnicodeText)
    raw_json: Mapped[str | None] = mapped_column(UnicodeText)
    actor: Mapped[str] = mapped_column(Unicode(200), default="collector")


class Review(Base):
    __tablename__ = "reviews"
    opportunity_id: Mapped[str] = mapped_column(ForeignKey("opportunities.id"), primary_key=True)
    eligibility: Mapped[str] = mapped_column(String(30), default="unreviewed")
    city_role: Mapped[str] = mapped_column(String(30), default="unknown")
    service_area: Mapped[str] = mapped_column(Unicode(200), default="")
    notes: Mapped[str] = mapped_column(UnicodeText, default="")
    evidence_url: Mapped[str] = mapped_column(Unicode(2048), default="")
    reviewed_source_version: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    updated_by: Mapped[str] = mapped_column(Unicode(200))


class PageSnapshot(Base):
    __tablename__ = "page_snapshots"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    url: Mapped[str] = mapped_column(Unicode(2048))
    text_hash: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(UnicodeText)
    html_gzip: Mapped[bytes] = mapped_column(LargeBinary)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime)


class Rejection(Base):
    __tablename__ = "rejected_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("collection_runs.id"))
    reason: Mapped[str] = mapped_column(UnicodeText)
    raw_json: Mapped[str] = mapped_column(UnicodeText)


class Lease(Base):
    __tablename__ = "leases"
    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    owner: Mapped[str] = mapped_column(String(36))
    expires_at: Mapped[datetime] = mapped_column(DateTime)


# A single canonical URL gives a stable UUID. Matching titles alone never merges calls.
# No cascade deletes: public evidence and review history are retained deliberately.

metadata = Base.metadata

STATUS_SQL = """CASE
 WHEN o.source_status = 'cancelled' THEN 'cancelled'
 WHEN o.deadline_expires_at IS NOT NULL AND o.deadline_expires_at <= CURRENT_TIMESTAMP THEN 'closed'
 WHEN o.deadline_at IS NOT NULL AND o.deadline_at < CURRENT_TIMESTAMP THEN 'closed'
 WHEN o.deadline_on IS NOT NULL AND o.deadline_on < CAST(CURRENT_TIMESTAMP AS DATE) THEN 'closed'
 WHEN o.source_status = 'closed' THEN 'closed'
 WHEN o.opens_on IS NOT NULL AND o.opens_on > CAST(CURRENT_TIMESTAMP AS DATE) THEN 'forthcoming'
 ELSE o.source_status END"""


def view_statements(dialect):
    status = STATUS_SQL
    if dialect == "sqlite":
        status = status.replace("CAST(CURRENT_TIMESTAMP AS DATE)", "DATE(CURRENT_TIMESTAMP)")
    elif dialect == "mssql":
        status = status.replace("CURRENT_TIMESTAMP", "SYSUTCDATETIME()")
    yield f"""CREATE VIEW v_funding AS SELECT o.*,
        {status} AS effective_status,
        COALESCE(r.eligibility, 'unreviewed') AS eligibility,
        COALESCE(r.city_role, 'unknown') AS city_role,
        COALESCE(r.service_area, '') AS service_area,
        COALESCE(r.notes, '') AS review_notes,
        CASE WHEN r.opportunity_id IS NULL OR r.eligibility = 'unreviewed' OR r.reviewed_source_version <> o.version THEN 1 ELSE 0 END AS needs_review,
        s.name AS source_name, s.health AS source_health, s.last_success_at AS source_last_success_at
        FROM opportunities o JOIN sources s ON s.id=o.source_id
        LEFT JOIN reviews r ON r.opportunity_id=o.id"""
    yield "CREATE VIEW v_funding_tags AS SELECT opportunity_id, kind, value, basis FROM opportunity_tags"
    yield "CREATE VIEW v_source_health AS SELECT id, name, category, adapter, enabled, health, last_attempt_at, last_success_at, last_error, coverage FROM sources"
