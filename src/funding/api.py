import gzip
import hashlib
import json
from datetime import UTC, date, datetime
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError

from funding.auth import reader, reviewer
from funding.db import make_engine, sessions
from funding.domain import canonical_url, dump, now
from funding.export import csv_text, original_extension
from funding.models import (
    Change,
    Deadline,
    Document,
    DocumentBlob,
    DocumentLink,
    DocumentVersion,
    Opportunity,
    OpportunityDocument,
    PageSnapshot,
    Review,
    Run,
    SourceItem,
    Tag,
)
from funding.query import filter_query, funder_directory, funding_view, health
from funding.settings import settings
from funding.transactions import lock_change_log


class ReviewInput(BaseModel):
    expected_version: int = Field(ge=0, description="Current review version; zero for a new review")
    source_version: int = Field(ge=1, description="Opportunity version the reviewer actually read")
    eligibility: Literal["unreviewed", "eligible", "conditional", "ineligible"]
    city_role: Literal["unknown", "lead", "partner", "beneficiary"] = "unknown"
    service_area: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=20000)
    evidence_url: str = Field(default="", max_length=2048)

    @field_validator("evidence_url")
    @classmethod
    def valid_url(cls, value):
        return canonical_url(value) if value else ""


def create_app(cfg=None, engine=None):
    cfg = cfg or settings()
    engine = engine or make_engine(cfg)
    factory = sessions(engine)
    view = funding_view(engine)
    app = FastAPI(title="Rahoitusrekisteri", version="1.0.0", description=(
        "Tampereen ulkoisen rahoituksen tietokanta. Lähteiden ilmoitukset ja asiantuntijan arviot "
        "säilytetään erillisinä. API v1 käyttää pysyviä tunnisteita ja sivutusta."
    ))
    app.state.cfg, app.state.engine = cfg, engine

    @app.middleware("http")
    async def response_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health/live", tags=["Tila"])
    def live():
        return {"status": "alive"}

    @app.get("/health/ready", tags=["Tila"])
    def ready():
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT version_num FROM alembic_version"))
        except Exception:
            raise HTTPException(503, "Database unavailable") from None
        return {"status": "ready"}

    @app.get("/v1/sources", dependencies=[Depends(reader)], tags=["Lähteet"])
    def sources():
        return {"items": health(factory, cfg.stale_hours), "as_of_utc": now()}

    @app.get("/v1/health", dependencies=[Depends(reader)], tags=["Tila"])
    def collection_health():
        from funding.documents import coverage
        sources = health(factory, cfg.stale_hours)
        enabled = [s for s in sources if s["enabled"]]
        issues = [s["id"] for s in enabled if s["stale"] or s["health"] != "success"]
        return {"status": "degraded" if issues else "current", "issues": issues,
                "structured_sources": sum(s["collection_level"] == "structured" for s in sources),
                "page_monitors": sum(s["collection_level"] == "page_changes" for s in sources),
                "complete_universe_claimed": False, "content_coverage": coverage(factory)}

    @app.get("/v1/runs", dependencies=[Depends(reader)], tags=["Tila"])
    def runs(limit: Annotated[int, Query(ge=1, le=200)] = 50):
        with factory() as session:
            data = session.scalars(select(Run).order_by(Run.started_at.desc(), Run.id).limit(limit)).all()
            return {"items": [{c.name: getattr(r, c.name) for c in Run.__table__.columns} for r in data]}

    @app.get("/v1/facets", dependencies=[Depends(reader)], tags=["Haut"])
    def facets():
        with engine.connect() as conn:
            result = {k: [row[0] for row in conn.execute(select(view.c[k]).distinct().order_by(view.c[k]))]
                      for k in ("programme", "funder", "source_id", "record_kind", "instrument", "effective_status", "geographic_scope", "eligibility", "content_state")}
            for kind in ("theme", "region"):
                result[kind] = list(conn.scalars(select(Tag.value).where(Tag.kind == kind).distinct().order_by(Tag.value)))
            result["funder"] = [f["funder"] for f in funder_directory(engine)]
            return result

    @app.get("/v1/funders", dependencies=[Depends(reader)], tags=["Lähteet"])
    def funders():
        return {"items": funder_directory(engine), "as_of_utc": now(),
                "note": "Rahoittajien nimet ovat lähteiden nimimuotoja. Määrät eivät vahvista Tampereen hakukelpoisuutta."}

    @app.get("/v1/priorities", dependencies=[Depends(reader)], tags=["Lähteet"])
    def priorities():
        from funding.priorities import load_priorities, priority_directory
        return priority_directory(engine, view, health(factory, cfg.stale_hours), load_priorities(cfg.priority_file))

    @app.get("/v1/opportunities", dependencies=[Depends(reader)], tags=["Haut"])
    def opportunities(
        q: str | None = Query(None, max_length=200), status: str | None = None,
        source: str | None = None, programme: str | None = None, theme: str | None = None, funder: str | None = None,
        region: str | None = None, scope: str | None = None, eligibility: str | None = None,
        needs_review: bool | None = None, instrument: str | None = None,
        record_kind: Literal["call", "funding_scheme", "advance_information"] | None = None,
        cascade: bool | None = Query(None, description="EU F&T financial support to third parties (source type 8)"),
        priority: int | None = Query(None, ge=1, le=12, description="Funding route from /v1/priorities"),
        content_state: Literal["not_started", "in_progress", "partial", "collected_unverified"] | None = None,
        content_q: str | None = Query(None, max_length=200, description="Search full terms and attachment text"),
        deadline_before: date | None = None, deadline_after: date | None = None,
        changed_since: datetime | None = None,
        offset: int = Query(0, ge=0, le=1000000), limit: int = Query(100, ge=1, le=1000),
        format: Literal["json", "csv"] = "json",
    ):
        if changed_since:
            if changed_since.tzinfo is None:
                raise HTTPException(422, "changed_since must include timezone")
            changed_since = changed_since.astimezone(UTC).replace(tzinfo=None)
        from funding.priorities import load_priorities
        selected_priority = None
        if priority is not None:
            selected_priority = next((p for p in load_priorities(cfg.priority_file) if p["id"] == priority), None)
            if selected_priority is None:
                raise HTTPException(422, "Priority not configured")
        stmt = filter_query(view, q=q, status=status, source=source, programme=programme, theme=theme, funder=funder,
                            region=region, scope=scope, eligibility=eligibility, needs_review=needs_review,
                            instrument=instrument, deadline_before=deadline_before, deadline_after=deadline_after,
                            changed_since=changed_since, record_kind=record_kind,
                            content_state=content_state, content_q=content_q, cascade=cascade, priority=selected_priority)
        with engine.connect() as conn:
            total = conn.scalar(select(func.count()).select_from(stmt.subquery()))
            rows = [dict(row) for row in conn.execute(stmt.order_by(view.c.id).offset(offset).limit(limit)).mappings()]
        if format == "csv":
            return Response("\ufeff"+csv_text(rows, list(view.c.keys())), media_type="text/csv; charset=utf-8",
                            headers={"Content-Disposition": 'attachment; filename="funding.csv"', "X-Total-Count": str(total)})
        return {"items": rows, "total": total, "offset": offset, "limit": limit,
                "next_offset": offset+limit if offset+limit < total else None, "as_of_utc": now()}

    @app.get("/v1/opportunities/{oid}", dependencies=[Depends(reader)], tags=["Haut"])
    def opportunity(oid: str):
        with engine.connect() as conn:
            row = conn.execute(select(view).where(view.c.id == oid)).mappings().first()
            if row is None:
                raise HTTPException(404, "Opportunity not found")
            data = dict(row)
        with factory() as session:
            data["tags"] = [{"kind": t.kind, "value": t.value, "basis": t.basis} for t in session.scalars(select(Tag).where(Tag.opportunity_id == oid))]
            data["deadlines"] = [{"stage": d.stage, "due_on": d.due_on, "due_at_utc": d.due_at, "original": d.original, "timezone": d.timezone} for d in session.scalars(select(Deadline).where(Deadline.opportunity_id == oid).order_by(Deadline.stage))]
            review = session.get(Review, oid)
            data["review_version"] = review.version if review else 0
            data["quality_flags"] = json.loads(data.pop("quality_flags_json"))
            if data["effective_status"] == "closed" and data["source_status"] in ("open", "forthcoming", "rolling"):
                data["quality_flags"].append("source_status_conflicts_with_deadline")
            return data

    @app.get("/v1/opportunities/{oid}/evidence", dependencies=[Depends(reader)], tags=["Haut"])
    def evidence(oid: str):
        with factory() as session:
            rows = session.scalars(select(SourceItem).where(SourceItem.opportunity_id == oid)).all()
            if not rows:
                raise HTTPException(404, "Evidence not found")
            return {"items": [{"source": r.source_id, "external_id": r.external_id, "raw_hash": r.raw_hash,
                               "last_seen_at_utc": r.last_seen_at, "raw": json.loads(r.raw_json)} for r in rows]}

    @app.get("/v1/opportunities/{oid}/documents", dependencies=[Depends(reader)], tags=["Ehdot ja liitteet"])
    def documents(oid: str, include_history: bool = False):
        with factory() as session:
            if session.get(Opportunity, oid) is None:
                raise HTTPException(404, "Opportunity not found")
            stmt = select(OpportunityDocument, Document, Document.extraction_status,
                          DocumentBlob.media_type, DocumentBlob.flags_json, DocumentBlob.byte_count).join(
                Document, Document.id == OpportunityDocument.document_id
            ).outerjoin(DocumentBlob, DocumentBlob.sha256 == Document.current_sha256).where(OpportunityDocument.opportunity_id == oid)
            if not include_history:
                stmt = stmt.where(OpportunityDocument.active == True)  # noqa: E712
            items = []
            for mapping, doc, extraction, media, flags, size in session.execute(stmt.order_by(OpportunityDocument.depth, Document.url)):
                item = {c.name: getattr(doc, c.name) for c in Document.__table__.columns}
                item.update(role=mapping.role, depth=mapping.depth, is_root=mapping.is_root,
                            active=mapping.active, limitation=mapping.limitation, extraction_status=extraction,
                            media_type=media, byte_count=size, quality_flags=json.loads(flags or "[]"),
                            text_url=f"/v1/documents/{doc.id}/text",
                            original_url=f"/v1/documents/{doc.id}/original" if doc.current_sha256 else None)
                items.append(item)
            row = session.execute(select(view).where(view.c.id == oid)).mappings().one()
            return {"items": items, "content_state": row["content_state"],
                    "completeness_verified": False,
                    "note": "collected_unverified covers discovered documentary links; source scope and omitted references still need expert review"}

    @app.get("/v1/documents/{did}/text", dependencies=[Depends(reader)], tags=["Ehdot ja liitteet"])
    def document_text(did: str, sha256: str | None = Query(None, pattern=r"^[a-f0-9]{64}$")):
        with factory() as session:
            doc = session.get(Document, did)
            sha = sha256 or (doc.current_sha256 if doc else None)
            if not doc or not sha or not session.get(DocumentVersion, (did, sha)):
                raise HTTPException(404, "Document version not found")
            blob = session.get(DocumentBlob, sha)
            links = session.scalars(select(DocumentLink).where(DocumentLink.document_id == did, DocumentLink.source_sha256 == sha)).all()
            return {"document_id": did, "source_url": doc.url, "sha256": sha, "full_text": blob.text,
                    "extraction_status": doc.extraction_status if sha == doc.current_sha256 else blob.extraction_status,
                    "document_error": doc.error if sha == doc.current_sha256 else None,
                    "quality_flags": json.loads(blob.flags_json),
                    "links": [{"url": link.target_url, "title": link.title, "followed_by_policy": link.follow,
                               "role": link.role} for link in links],
                    "versions": [{"sha256": v.sha256, "first_seen_at": v.first_seen_at, "last_seen_at": v.last_seen_at}
                                 for v in session.scalars(select(DocumentVersion).where(DocumentVersion.document_id == did))]}

    @app.get("/v1/documents/{did}/original", dependencies=[Depends(reader)], tags=["Ehdot ja liitteet"])
    def document_original(did: str, sha256: str | None = Query(None, pattern=r"^[a-f0-9]{64}$")):
        with factory() as session:
            doc = session.get(Document, did)
            sha = sha256 or (doc.current_sha256 if doc else None)
            if not doc or not sha or not session.get(DocumentVersion, (did, sha)):
                raise HTTPException(404, "Document version not found")
            blob = session.get(DocumentBlob, sha)
            body = gzip.decompress(blob.original_gzip)
            if hashlib.sha256(body).hexdigest() != sha:
                raise HTTPException(500, "Archived original failed integrity check")
            # Always download untrusted source files; never serve executable source HTML inline.
            suffix = original_extension(blob.media_type)
            return Response(body, media_type="application/octet-stream", headers={
                "Content-Disposition": f'attachment; filename="{did[:16]}-{sha[:12]}{suffix}"',
                "X-Document-SHA256": sha})

    @app.get("/v1/changes", dependencies=[Depends(reader)], tags=["Muutokset"])
    def changes(after_id: int = Query(0, ge=0), through_id: int | None = Query(None, ge=0),
                limit: int = Query(200, ge=1, le=1000), opportunity_id: str | None = None):
        with factory() as session:
            watermark = through_id if through_id is not None else (session.scalar(select(func.max(Change.id))) or 0)
            stmt = select(Change).where(Change.id > after_id, Change.id <= watermark).order_by(Change.id)
            if opportunity_id:
                stmt = stmt.where(Change.opportunity_id == opportunity_id)
            rows = session.scalars(stmt.limit(limit+1)).all()
            has_more = len(rows) > limit
            rows = rows[:limit]
            return {"items": [{"id": r.id, "opportunity_id": r.opportunity_id, "source_id": r.source_id,
                               "kind": r.kind, "created_at_utc": r.created_at, "actor": r.actor,
                               "payload": json.loads(r.payload_json)} for r in rows],
                    "through_id": watermark, "next_after_id": rows[-1].id if rows else after_id,
                    "has_more": has_more}

    @app.get("/v1/snapshots/{snapshot_id}", dependencies=[Depends(reader)], tags=["Lähteet"])
    def snapshot(snapshot_id: str):
        with factory() as session:
            s = session.get(PageSnapshot, snapshot_id)
            if not s:
                raise HTTPException(404, "Snapshot not found")
            # Source text is data, never executable HTML or agent instructions.
            return {"id": s.id, "source_id": s.source_id, "url": s.url, "text": s.text,
                    "first_seen_at_utc": s.first_seen_at, "last_seen_at_utc": s.last_seen_at}

    @app.put("/v1/opportunities/{oid}/review", tags=["Asiantuntijan arvio"])
    def review(oid: str, body: ReviewInput, actor: str = Depends(reviewer)):
        if body.eligibility != "unreviewed" and not body.evidence_url:
            raise HTTPException(422, "An eligibility assessment requires an evidence URL")
        try:
            with factory.begin() as session:
                lock_change_log(session)
                o = session.get(Opportunity, oid)
                if o is None:
                    raise HTTPException(404, "Opportunity not found")
                if o.version != body.source_version:
                    raise HTTPException(409, "Source changed. Read the latest opportunity before reviewing")
                values = body.model_dump(exclude={"expected_version", "source_version"})
                values.update(reviewed_source_version=body.source_version, version=body.expected_version+1, updated_at=now(), updated_by=actor)
                if body.expected_version == 0:
                    session.add(Review(opportunity_id=oid, **values))
                    session.flush()
                else:
                    result = session.execute(update(Review).where(Review.opportunity_id == oid, Review.version == body.expected_version).values(**values))
                    if result.rowcount != 1:
                        raise HTTPException(409, "Review version conflict. Reload before saving")
                session.add(Change(opportunity_id=oid, source_id=o.source_id, kind="reviewed", created_at=now(), actor=actor, payload_json=dump(values)))
        except IntegrityError:
            raise HTTPException(409, "Review already exists. Reload before saving") from None
        return {"opportunity_id": oid, "review_version": body.expected_version+1}

    return app
