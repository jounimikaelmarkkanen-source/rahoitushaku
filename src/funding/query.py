from datetime import timedelta

from sqlalchemy import MetaData, Table, case, exists, func, select

from funding.domain import now
from funding.models import Document, DocumentBlob, OpportunityDocument, Source, Tag


def funding_view(engine):
    return Table("v_funding", MetaData(), autoload_with=engine)


def funder_directory(engine):
    view = funding_view(engine)
    stmt = select(
        func.min(view.c.funder).label("funder"),
        func.count().label("records"),
        func.sum(case((view.c.record_kind == "call", 1), else_=0)).label("calls"),
        func.sum(case((view.c.record_kind == "funding_scheme", 1), else_=0)).label("schemes"),
        func.sum(case((view.c.record_kind == "advance_information", 1), else_=0)).label("advance_information"),
        func.sum(case((view.c.effective_status.in_(["open", "forthcoming", "rolling"]), 1), else_=0)).label("open_or_forthcoming"),
        func.sum(case((view.c.effective_status == "unknown", 1), else_=0)).label("unknown_status"),
    ).where(view.c.funder != "").group_by(func.lower(view.c.funder)).order_by(func.min(view.c.funder))
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(stmt).mappings()]


def filter_query(view, *, q=None, status=None, source=None, programme=None, theme=None, funder=None,
                 region=None, scope=None, eligibility=None, needs_review=None,
                 deadline_before=None, deadline_after=None, changed_since=None, instrument=None, record_kind=None,
                 content_state=None, content_q=None, cascade=None, priority=None):
    stmt = select(view)
    if cascade is not None:
        cascade_condition = (view.c.source_id == "eu-funding") & view.c.external_id.startswith("cascade:", autoescape=True)
        stmt = stmt.where(cascade_condition if cascade else ~cascade_condition)
    if priority is not None:
        from funding.priorities import priority_predicate
        stmt = stmt.where(priority_predicate(view, priority))
    if q:
        stmt = stmt.where(func.lower(view.c.title + " " + view.c.description).contains(q.lower(), autoescape=True))
    for value, column in ((status, "effective_status"), (source, "source_id"), (programme, "programme"),
                          (scope, "geographic_scope"), (eligibility, "eligibility"), (instrument, "instrument"),
                          (record_kind, "record_kind"), (content_state, "content_state")):
        if value:
            stmt = stmt.where(view.c[column] == value)
    if funder:
        stmt = stmt.where(func.lower(view.c.funder) == funder.lower())
    for value, kind in ((theme, "theme"), (region, "region")):
        if value:
            stmt = stmt.where(exists(select(Tag.opportunity_id).where(Tag.opportunity_id == view.c.id, Tag.kind == kind, Tag.value == value)))
    if needs_review is not None:
        stmt = stmt.where(view.c.needs_review == int(needs_review))
    if deadline_before:
        stmt = stmt.where(view.c.deadline_on <= deadline_before)
    if deadline_after:
        stmt = stmt.where(view.c.deadline_on >= deadline_after)
    if changed_since:
        stmt = stmt.where(view.c.updated_at >= changed_since)
    if content_q:
        # Uncorrelated subqueries evaluate shared programme documents once, not once per call.
        matching_blobs = select(DocumentBlob.sha256).where(
            func.lower(DocumentBlob.text).contains(content_q.lower(), autoescape=True))
        matching_documents = select(Document.id).where(Document.current_sha256.in_(matching_blobs))
        stmt = stmt.where(view.c.id.in_(select(OpportunityDocument.opportunity_id).where(
            OpportunityDocument.active == True, OpportunityDocument.document_id.in_(matching_documents))))  # noqa: E712
    return stmt


def health(factory, stale_hours=36):
    with factory() as session:
        sources = session.scalars(select(Source).order_by(Source.id)).all()
        result = []
        for source in sources:
            stale = not source.last_success_at or source.last_success_at < now() - timedelta(hours=stale_hours)
            result.append({
                "id": source.id, "name": source.name, "url": source.url, "category": source.category,
                "adapter": source.adapter, "coverage": source.coverage, "enabled": source.enabled,
                "health": source.health, "stale": stale, "last_attempt_at": source.last_attempt_at,
                "last_success_at": source.last_success_at, "last_error": source.last_error,
                "collection_level": "page_changes" if source.adapter == "page_watch" else "manual" if source.adapter == "manual" else "structured",
            })
        return result
