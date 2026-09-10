import gzip
import json
import logging
from datetime import timedelta
from uuid import uuid4

from bs4 import BeautifulSoup
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from funding.adapters import ADAPTERS
from funding.domain import Record, digest, dump, enrich, now, opportunity_id
from funding.funders import FUNDERS
from funding.http import PublicClient
from funding.models import (
    Change,
    Deadline,
    Lease,
    Opportunity,
    PageSnapshot,
    Rejection,
    Run,
    Source,
    SourceItem,
    Tag,
)
from funding.transactions import lock_change_log

log = logging.getLogger(__name__)


def sync_sources(factory, path):
    entries = json.loads(path.read_text())
    ids = [x["id"] for x in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("Source IDs must be unique")
    with factory.begin() as session:
        for entry in entries:
            source = session.get(Source, entry["id"])
            if source is None:
                source = Source(id=entry["id"])
                session.add(source)
            for key in ("name", "url", "adapter", "category", "coverage", "owner", "enabled"):
                setattr(source, key, entry[key])
            source.config_json = dump(entry)


def acquire(factory, name, owner):
    with factory.begin() as session:
        updated = session.execute(update(Lease).where(Lease.name == name, Lease.expires_at < now()).values(owner=owner, expires_at=now()+timedelta(minutes=10)))
        if updated.rowcount:
            return True
    try:
        with factory.begin() as session:
            session.add(Lease(name=name, owner=owner, expires_at=now()+timedelta(minutes=10)))
        return True
    except IntegrityError:
        return False


def heartbeat(session, owner):
    result = session.execute(update(Lease).where(Lease.name == "collector", Lease.owner == owner).values(expires_at=now()+timedelta(minutes=10)))
    if result.rowcount != 1:
        raise RuntimeError("Collector lease lost")


def upsert(session, source_id, record: Record, raw: dict):
    lock_change_log(session)
    record = enrich(record)
    payload = record.model_dump(mode="json")
    content_hash = digest(dump(payload))
    oid, stamp = opportunity_id(record.canonical_url), now()
    item_id = digest(source_id + ":" + record.external_id)
    existing_item = session.get(SourceItem, item_id)
    # Preserve identity if a publisher changes the canonical URL.
    if existing_item:
        oid = existing_item.opportunity_id
    opportunity = session.get(Opportunity, oid)
    new = opportunity is None
    if new:
        opportunity = Opportunity(id=oid, source_id=source_id, first_seen_at=stamp, version=0)
        session.add(opportunity)
    elif opportunity.source_id == source_id and record.record_kind == "call":
        legacy_hash = digest(dump({key: value for key, value in payload.items() if key != "record_kind"}))
        if opportunity.record_kind == "call" and opportunity.content_hash == legacy_hash:
            # Migration 0002 adds a default field, not a publisher change. Preserve
            # existing reviews and versions when the next daily collection runs.
            opportunity.content_hash = content_hash
    raw_changed = existing_item is not None and existing_item.raw_hash != digest(dump(raw))
    changed = (new or opportunity.content_hash != content_hash or raw_changed) and opportunity.source_id == source_id
    if changed:
        fields = record.model_dump(exclude={"tags", "deadlines", "quality_flags"})
        for key, value in fields.items():
            setattr(opportunity, key, value)
        opportunity.quality_flags_json = dump(record.quality_flags)
        opportunity.content_hash = content_hash
        opportunity.updated_at = stamp
        opportunity.version += 1
        opportunity.last_seen_at = stamp
        session.flush()
        session.execute(delete(Tag).where(Tag.opportunity_id == oid))
        session.execute(delete(Deadline).where(Deadline.opportunity_id == oid))
        session.add_all(Tag(opportunity_id=oid, **tag.model_dump()) for tag in record.tags)
        session.add_all(Deadline(opportunity_id=oid, stage=i+1, **d.model_dump()) for i, d in enumerate(record.deadlines))
        session.add(Change(opportunity_id=oid, source_id=source_id, kind="created" if new else "updated", created_at=stamp, payload_json=dump(payload), raw_json=dump(raw)))
    if opportunity.source_id == source_id:
        opportunity.last_seen_at = stamp
    session.flush()
    item = existing_item or SourceItem(id=item_id, source_id=source_id, external_id=record.external_id, opportunity_id=oid)
    item.raw_json, item.raw_hash, item.last_seen_at = dump(raw), digest(dump(raw)), stamp
    if not existing_item:
        session.add(item)
    return changed


def watch_page(session, source, client):
    config = json.loads(source.config_json)
    r = client.request("GET", source.url)
    if "html" not in r.headers.get("content-type", ""):
        raise ValueError("Expected HTML for page monitor")
    soup = BeautifulSoup(r.text, "html.parser")
    main = soup.select_one(config.get("selector", "main, article"))
    if not main:
        raise ValueError("Expected main content selector missing")
    for node in main.select("script,style,nav,footer,form,noscript"):
        node.decompose()
    text = main.get_text("\n", strip=True)
    if len(text) < 100:
        raise ValueError("Page content too short; possible error or bot challenge")
    signature = digest(text)
    sid = digest(source.id + ":" + signature)
    existing = session.get(PageSnapshot, sid)
    previous = session.scalar(select(PageSnapshot).where(PageSnapshot.source_id == source.id).order_by(PageSnapshot.last_seen_at.desc()).limit(1))
    if existing:
        existing.last_seen_at = now()
    else:
        session.add(PageSnapshot(id=sid, source_id=source.id, url=str(r.url), text_hash=signature, text=text, html_gzip=gzip.compress(r.content), first_seen_at=now(), last_seen_at=now()))
    changed = previous is None or previous.text_hash != signature
    if changed:
        lock_change_log(session)
        links = [{"title": a.get_text(" ", strip=True), "url": str(r.url.join(a["href"]))} for a in main.select("a[href]") if a.get_text(strip=True)]
        session.add(Change(source_id=source.id, kind="source_discovered" if previous is None else "source_changed", created_at=now(), payload_json=dump({"snapshot_id": sid, "url": str(r.url), "links": links, "triage_required": True})))
    return int(changed)


def collect(factory, cfg, source_ids=None, client_factory=PublicClient):
    owner = str(uuid4())
    if not acquire(factory, "collector", owner):
        raise RuntimeError("Another collector owns the database lease")
    outcomes = []
    try:
        with factory() as session:
            sources = session.scalars(select(Source).where(Source.enabled == True).order_by(Source.id)).all()  # noqa: E712
            source_list = [(s.id, json.loads(s.config_json)) for s in sources if source_ids is None or s.id in source_ids]
        if source_ids and set(source_ids) - {s[0] for s in source_list}:
            raise ValueError("Unknown or disabled source ID")
        for source_id, config in source_list:
            rid, warnings, seen, changed, rejected = str(uuid4()), [], 0, 0, 0
            client = client_factory(cfg, config["allowed_hosts"])
            with factory.begin() as session:
                heartbeat(session, owner)
                session.add(Run(id=rid, source_id=source_id, started_at=now()))
                source = session.get(Source, source_id)
                source.last_attempt_at = now()
            try:
                if config["adapter"] == "page_watch":
                    with factory.begin() as session:
                        changed = watch_page(session, session.get(Source, source_id), client)
                        seen = 1
                else:
                    for batch in {**ADAPTERS, **FUNDERS}[config["adapter"]](client, config):
                        with factory.begin() as session:
                            heartbeat(session, owner)
                            for record, raw in batch.items:
                                changed += int(upsert(session, source_id, record, raw))
                                seen += 1
                            for reason, raw in batch.rejected:
                                session.add(Rejection(run_id=rid, reason=reason, raw_json=dump(raw)))
                                rejected += 1
                            warnings.extend(batch.warnings)
                            run = session.get(Run, rid)
                            run.expected, run.seen, run.changed, run.rejected = batch.expected, seen, changed, rejected
                    if seen == 0:
                        raise ValueError("Unexpected empty collection; source must be checked")
                    if config.get("watch_catalogue"):
                        with factory.begin() as session:
                            heartbeat(session, owner)
                            watch_page(session, session.get(Source, source_id), client)
                status = "partial" if rejected or warnings else "success"
                message = "; ".join(sorted(set(warnings))) or (f"{rejected} records rejected" if rejected else None)
            except Exception as exc:
                status = "partial" if seen else "failed"
                # No connection strings, response bodies, or tracebacks in public operational output.
                message = f"{type(exc).__name__}: {str(exc)[:1200]}"
                log.warning("Source %s: %s", source_id, message)
            finally:
                client.close()
            with factory.begin() as session:
                heartbeat(session, owner)
                run = session.get(Run, rid)
                run.status, run.message, run.finished_at = status, message, now()
                run.seen, run.changed, run.rejected = seen, changed, rejected
                source = session.get(Source, source_id)
                source.health, source.last_error = status, message
                if status == "success":
                    source.last_success_at = now()
            result = dict(source=source_id, status=status, seen=seen, changed=changed, rejected=rejected, message=message)
            outcomes.append(result)
            print(dump(result), flush=True)
    finally:
        with factory.begin() as session:
            session.execute(delete(Lease).where(Lease.name == "collector", Lease.owner == owner))
    return outcomes
