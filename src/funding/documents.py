"""Resumable, bounded public-document backfill and daily refresh."""
import gzip
import hashlib
import html
import json
import re
import threading
import time
from collections import defaultdict, deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import nullcontext
from datetime import datetime, timedelta
from urllib.parse import quote, urlsplit
from uuid import uuid4

import httpx
from sqlalchemy import and_, case, delete, func, or_, select, update

from funding.collector import acquire, heartbeat
from funding.document_parsers import DOCUMENT, Link, Parsed, document_url, infer_media_type, parse_document
from funding.domain import digest, dump, now
from funding.http import PublicClient, RateLimited
from funding.models import (
    Change,
    Document,
    DocumentBlob,
    DocumentLink,
    DocumentVersion,
    Lease,
    Opportunity,
    OpportunityDocument,
    SourceItem,
)
from funding.transactions import lock_change_log


def next_daily_check(stamp):
    return (stamp+timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


RESPONSE_ISSUES = ("DOCUMENT_DOWNLOAD_RETURNED_HTML", "DETAIL_REDIRECTED_TO_FRONT_PAGE")


def document_response_issue(url, media, final_url=None):
    if media not in ("text/html", "application/xhtml+xml"):
        return None
    if DOCUMENT.search(url):
        return RESPONSE_ISSUES[0]
    if final_url:
        old, new = urlsplit(url), urlsplit(final_url)
        if len(old.path.strip("/").split("/")) >= 2 and new.path.strip("/") in ("", "fi", "en", "sv"):
            return RESPONSE_ISSUES[1]
    return None


def mark_missing_attachment(url, media, parsed, final_url=None):
    if document_response_issue(url, media, final_url):
        # Landing pages and access challenges are not the linked attachment.
        for link in parsed.links:
            link.follow = False


def has_published_text(values):
    return any(isinstance(value, str) and html.unescape(re.sub(r"<[^>]*>", "", value)).strip()
               for value in (values if isinstance(values, list) else [values]))


def eu_has_content(raw):
    if isinstance(raw, bytes):
        try:
            raw = json.loads(raw)
        except ValueError:
            return False
    if not isinstance(raw, dict):
        return False
    keys = ("topicConditions", "descriptionByte", "caConditions", "caDescription", "description", "beneficiaryAdministration")
    for row in raw.get("documents", [raw]):
        metadata = row.get("metadata", {})
        for key in keys:
            if has_published_text(metadata.get(key, [])):
                return True
    return False


def mark_eu_completeness(raw, parsed, base):
    """Expose missing source text and try detail URLs explicitly published by the source."""
    if isinstance(raw, bytes):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = {}
    if eu_has_content(raw):
        return
    if parsed.status == "extracted":
        parsed.status = "partial_text"
    flag = "full_eu_conditions_not_present_in_source_entry"
    if flag not in parsed.flags:
        parsed.flags.append(flag)
    if not isinstance(raw, dict):
        return
    for row in raw.get("documents", [raw]):
        urls = row.get("metadata", {}).get("url", [])
        urls = urls if isinstance(urls, list) else [urls]
        for href in [row.get("url"), *urls]:
            target = document_url(href, base) if isinstance(href, str) else None
            if not target or target == document_url(base):
                continue
            link = next((item for item in parsed.links if item.url == target), None)
            if link:
                link.follow = True
                link.role = "source_detail_fallback"
            else:
                parsed.links.append(Link(target, "EU-haun lähteessä ilmoitettu lisätietovastaus",
                                         "source_detail_fallback", True))


def mark_faq_completeness(raw, parsed, base):
    """An archived FAQ with an empty answer must remain visibly incomplete after refresh."""
    if isinstance(raw, bytes):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = {}
    meta = raw.get("metadata", {}) if isinstance(raw, dict) else {}
    if all(has_published_text(meta.get(key, [])) for key in ("question", "answer")):
        return
    if parsed.status == "extracted":
        parsed.status = "partial_text"
    flag = "full_faq_question_or_answer_not_published"
    if flag not in parsed.flags:
        parsed.flags.append(flag)
    ids = meta.get("nid", [])
    nid = ids[0] if isinstance(ids, list) and ids else ids
    if not isinstance(nid, str) or not nid.isdigit():
        return
    target = "https://api.tech.ec.europa.eu/search-api/prod/rest/document/"+nid+"?apiKey=SEDIA_FAQ"
    if target == document_url(base):
        return
    link = next((item for item in parsed.links if item.url == target), None)
    if link:
        link.follow, link.role, link.parser = True, "faq_detail_fallback", "eu_faq_detail"
    else:
        parsed.links.append(Link(target, "FAQ-kysymyksen julkinen lisätietovastaus",
                                 "faq_detail_fallback", True, "eu_faq_detail"))


class DocumentClient(PublicClient):
    """Follow discovered public documentary links, checking every redirect and DNS address."""
    pace_lock = threading.Lock()
    starts = {}
    robots_lock = threading.Lock()
    robots_origin_locks = {}
    robots_cache = {}

    def validate(self, url):
        host = urlsplit(url).hostname
        if host:
            self.allowed_hosts.add(host)
        super().validate(url)

    def _request(self, method, url, **kwargs):
        host = urlsplit(url).hostname
        p = urlsplit(url)
        robot = self.robots.get(f"{p.scheme}://{p.netloc}")
        delay = (robot.crawl_delay(self.cfg.user_agent) or robot.crawl_delay("*") or 0) if robot else 0
        with self.pace_lock:
            start = max(time.monotonic(), self.starts.get(host, 0)+max(delay, self.cfg.min_request_interval))
            self.starts[host] = start
        time.sleep(max(0, start-time.monotonic()))
        return super()._request(method, url, **kwargs)

    def _robots_allowed(self, url):
        # Load each origin once; the parent enforces disallow and crawl-delay on every request.
        p = urlsplit(url)
        origin = f"{p.scheme}://{p.netloc}"
        with self.robots_lock:
            lock = self.robots_origin_locks.setdefault(origin, threading.Lock())
        self.robots = self.robots_cache
        # A slow robots.txt service must not hold up unrelated funders.
        with lock:
            super()._robots_allowed(url)


def ensure_document(session, url, parser="web", title="", request_identity=""):
    did = digest(url+("\n"+request_identity if request_identity else ""))
    cache = session.info.setdefault("document_objects", {})
    with session.no_autoflush:
        doc = cache.get(did) or session.get(Document, did)
    if doc is None:
        doc = Document(id=did, url=url, parser=parser, title=title[:1000], state="pending", attempts=0)
        session.add(doc)
        session.flush([doc])
    elif doc.parser == "web" and parser != "web":
        doc.parser = parser
    cache[did] = doc
    return doc


def associate(session, oid, doc, depth=0, parent=None, role="call_content", root=False, limitation=None):
    key = (oid, doc.id)
    mapping = session.get(OpportunityDocument, key)
    if mapping is None:
        mapping = OpportunityDocument(opportunity_id=oid, document_id=doc.id,
                                      first_seen_at=now(), is_root=root)
        session.add(mapping)
    elif mapping.active and mapping.depth < depth:
        return mapping
    mapping.depth, mapping.parent_document_id, mapping.role = depth, parent, role
    mapping.active, mapping.limitation = True, limitation
    mapping.is_root = mapping.is_root or root
    return mapping


def persist(session, doc, body, media_type, parsed, final_url=None, headers=None, stamp=None, preserve_observation=False):
    media_type = infer_media_type(body, media_type)
    observed_fields = ("state", "checked_at", "last_success_at", "next_check_at", "final_url", "http_status", "error", "attempts", "etag", "last_modified")
    observation = {key: getattr(doc, key) for key in observed_fields} if preserve_observation else None
    event_stamp = now()
    stamp = stamp or event_stamp
    sha = hashlib.sha256(body).hexdigest()
    old_sha = doc.current_sha256
    old_extraction_status = doc.extraction_status
    response_issue = document_response_issue(doc.url, media_type,
        final_url or (doc.final_url if preserve_observation else doc.url))
    blob = session.get(DocumentBlob, sha)
    # Transport provenance is already stored in Document.url/final_url. It must
    # not toggle shared content metadata when HTTP and HTTPS aliases alternate.
    def shared_flags(flags):
        return dump([flag for flag in flags if flag != "source_http_link_retrieved_over_https"])
    flags_json = shared_flags(parsed.flags)
    extraction_changed = False
    if blob is None:
        blob = DocumentBlob(sha256=sha, original_gzip=gzip.compress(body, mtime=0),
                            byte_count=len(body), media_type=media_type[:200], text=parsed.text,
                            extraction_status=parsed.status, flags_json=flags_json,
                            page_count=parsed.page_count, created_at=stamp)
        session.add(blob)
        session.flush()
    elif (blob.text, blob.extraction_status, shared_flags(json.loads(blob.flags_json)), blob.media_type, blob.page_count) != (
            parsed.text, parsed.status, flags_json, media_type[:200], parsed.page_count):
        extraction_changed = True
        blob.text, blob.extraction_status, blob.flags_json = parsed.text, parsed.status, flags_json
        blob.page_count, blob.media_type = parsed.page_count, media_type[:200]
    else:
        blob.flags_json = flags_json
    doc.current_sha256, doc.state = sha, "fetched"
    doc.extraction_status = parsed.status
    if extraction_changed:
        session.execute(update(Document).where(Document.current_sha256 == sha,
            or_(Document.error.is_(None), Document.error.not_in(RESPONSE_ISSUES))).values(extraction_status=parsed.status))
    if response_issue:
        doc.extraction_status = "unreadable"
    doc.title = (parsed.title or doc.title)[:1000]
    doc.checked_at, doc.last_success_at = stamp, stamp
    doc.next_check_at = next_daily_check(stamp)
    doc.final_url, doc.http_status, doc.error = final_url or doc.url, 200, None
    if response_issue:
        doc.error = response_issue
    doc.attempts += 1
    if headers:
        doc.etag, doc.last_modified = headers.get("etag"), headers.get("last-modified")
    version = session.get(DocumentVersion, (doc.id, sha))
    if version is None:
        session.add(DocumentVersion(document_id=doc.id, sha256=sha, first_seen_at=stamp, last_seen_at=stamp))
    else:
        if not preserve_observation:
            version.last_seen_at = stamp
    existing_links = {link.id: link for link in session.scalars(select(DocumentLink).where(
        DocumentLink.document_id == doc.id, DocumentLink.source_sha256 == sha))}
    for link in existing_links.values():
        link.follow = False
    for link in parsed.links:
        lid = digest(doc.id+sha+link.url)
        if lid not in existing_links:
            session.add(DocumentLink(id=lid, document_id=doc.id, source_sha256=sha,
                                     target_url=link.url, title=link.title[:1000], role=link.role,
                                     follow=link.follow, parser=link.parser))
        else:
            existing = existing_links[lid]
            existing.follow, existing.parser, existing.role, existing.title = link.follow, link.parser, link.role, link.title[:1000]
    if old_sha != sha or extraction_changed or old_extraction_status != doc.extraction_status:
        # A review made before the new conditions were read must not remain current.
        lock_change_log(session)
        affected_documents = select(Document.id).where(Document.current_sha256 == sha) if extraction_changed else [doc.id]
        affected = select(OpportunityDocument.opportunity_id).where(
            OpportunityDocument.document_id.in_(affected_documents), OpportunityDocument.active == True)  # noqa: E712
        opportunities = session.execute(select(Opportunity.id, Opportunity.source_id).where(Opportunity.id.in_(affected))).all()
        if opportunities:
            # A shared programme guide can affect thousands of calls. Update versions
            # in one statement and insert bounded change batches without loading their descriptions.
            session.execute(update(Opportunity).where(Opportunity.id.in_(affected)).values(
                version=Opportunity.version+1, updated_at=event_stamp), execution_options={"synchronize_session": "fetch"})
            event = {
                "kind": ("document_reextracted" if old_sha == sha else "document_updated") if old_sha else "document_added",
                "created_at": event_stamp, "actor": "document_collector",
                "payload_json": dump({"document_id": doc.id, "url": doc.url, "previous_sha256": old_sha,
                                      "sha256": sha, "extraction_status": doc.extraction_status}),
            }
            for start in range(0, len(opportunities), 100):
                session.execute(Change.__table__.insert().values([
                    {"opportunity_id": oid, "source_id": source, **event}
                    for oid, source in opportunities[start:start+100]
                ]))
    if observation:
        for key, value in observation.items():
            setattr(doc, key, value)
        if response_issue and doc.state == "fetched":
            doc.error = response_issue
    return old_sha != sha or extraction_changed or old_extraction_status != doc.extraction_status


def current_opportunities(stamp):
    """Include potentially current/unknown calls, excluding expired and cancelled ones."""
    return and_(Opportunity.source_status.not_in(("closed", "cancelled")),
                or_(Opportunity.deadline_expires_at.is_(None), Opportunity.deadline_expires_at > stamp),
                or_(Opportunity.deadline_at.is_(None), Opportunity.deadline_at >= stamp),
                or_(Opportunity.deadline_on.is_(None), Opportunity.deadline_on >= stamp.date()))


def seed(factory, source_ids=None, current_only=False, stamp=None):
    with factory() as session:
        stmt = select(Opportunity.id, Opportunity.source_id, Opportunity.external_id, Opportunity.canonical_url)
        if source_ids:
            stmt = stmt.where(Opportunity.source_id.in_(source_ids))
        if current_only:
            stmt = stmt.where(current_opportunities(stamp or now()))
        rows = session.execute(stmt).all()
    for start in range(0, len(rows), 100):
        with factory.begin() as session:
            for oid, source, ext, url in rows[start:start+100]:
                if source == "haeavustuksia":
                    prefix = "https://www.haeavustuksia.fi/api/haku/"+quote(ext, safe="")+"/hakuilmoitus/"
                    roots = [(prefix+s, "hae_json", s) for s in (
                        "yleistiedot", "hakuaika", "perustiedot", "myontoperusteet", "arviointiperusteet", "lisaehdot")]
                else:
                    roots = [(url, "eura" if source == "eura2021" else "eu_source" if source == "eu-funding" else "web", "Hakuilmoitus")]
                for root_url, parser, label in roots:
                    doc = ensure_document(session, root_url, parser, label)
                    associate(session, oid, doc, root=True)
    return [row[0] for row in rows]


def refresh_graph(factory, opportunity_ids, max_depth=4, max_documents=250, known_documents=None, owner=None):
    """Rebuild current reachability. Removed links remain in history but leave the current package."""
    with factory() as session:
        # Pending documents cannot have current outgoing links. Avoid a separate empty
        # database query for every pending attachment shared by thousands of calls.
        edges = {did: [] for did in session.scalars(select(Document.id).where(Document.current_sha256.is_(None)))}
        if known_documents is None:
            known_documents = set(session.scalars(select(Document.id)))
    for start in range(0, len(opportunity_ids), 50):
        ids = opportunity_ids[start:start+50]
        with factory.begin() as session:
            # Reachability is computed before changing the stored active flags. An
            # autoflush during an edge lookup would write temporary inactive states.
            session.autoflush = False
            maps = session.scalars(select(OpportunityDocument).where(OpportunityDocument.opportunity_id.in_(ids))).all()
            roots = defaultdict(list)
            existing = {(m.opportunity_id, m.document_id): m for m in maps}
            for mapping in maps:
                mapping.active = False
                if mapping.is_root:
                    roots[mapping.opportunity_id].append(mapping)
            for oid in ids:
                queue, seen = deque(), set()
                document_limit_recorded = False
                for mapping in roots[oid]:
                    mapping.active = True
                    seen.add(mapping.document_id)
                    queue.append((mapping.document_id, 0))
                while queue:
                    parent, depth = queue.popleft()
                    if parent not in edges:
                        edges[parent] = session.execute(select(DocumentLink.target_url, DocumentLink.parser,
                            DocumentLink.title, DocumentLink.role).join(Document, and_(
                            Document.id == DocumentLink.document_id,
                            Document.current_sha256 == DocumentLink.source_sha256
                        )).where(DocumentLink.document_id == parent, DocumentLink.follow == True)).all()  # noqa: E712
                    for link in edges[parent]:
                        did = digest(link.target_url)
                        if did in seen:
                            continue
                        seen.add(did)
                        limitation = "depth_limit" if depth+1 > max_depth else (
                            "document_limit" if len(seen) > max_documents else None)
                        if len(seen) > max_documents:
                            if document_limit_recorded:
                                continue
                            limitation = "document_limit"
                            document_limit_recorded = True
                        if did not in known_documents:
                            ensure_document(session, link.target_url, link.parser, link.title)
                            known_documents.add(did)
                            edges[did] = []
                        mapping = existing.get((oid, did))
                        if mapping is None:
                            mapping = OpportunityDocument(opportunity_id=oid, document_id=did,
                                depth=depth+1, parent_document_id=parent, role=link.role, limitation=limitation,
                                is_root=False, active=True, first_seen_at=now())
                            session.add(mapping)
                            existing[(oid, did)] = mapping
                        else:
                            mapping.active, mapping.depth, mapping.parent_document_id = True, depth+1, parent
                            mapping.limitation, mapping.role = limitation, link.role
                        if limitation is None:
                            queue.append((did, depth+1))
            if owner:
                heartbeat(session, owner)


def fetch_document(cfg, row, client_factory=DocumentClient):
    client = client_factory(cfg, [])
    try:
        headers = {}
        if row["parser"] == "hae_json":
            headers["Accept"] = "application/json"
        if row["etag"]:
            headers["If-None-Match"] = row["etag"]
        if row["last_modified"]:
            headers["If-Modified-Since"] = row["last_modified"]
        url = row["url"]
        upgraded = url.startswith("http://")
        if upgraded:
            url = "https://"+url[len("http://"):]
        if row["parser"] == "eu_faq_source":
            nid = url.rstrip("/").rsplit("/", 1)[-1]
            url = "https://api.tech.ec.europa.eu/search-api/prod/rest/document/"+quote(nid, safe="")+"?apiKey=SEDIA_FAQ"
        response = client.request("GET", url, headers=headers)
        if response.status_code == 304:
            return {"not_modified": True}
        media = infer_media_type(response.content, response.headers.get("content-type", "application/octet-stream").split(";", 1)[0])
        try:
            parsed = parse_document(response.content, media, str(response.url), row["parser"])
        except Exception as exc:
            parsed = Parsed(status="unreadable", flags=["parser_error:"+type(exc).__name__+":"+str(exc)[:300]])
        if row["parser"] in ("eu_faq_source", "eu_faq_detail"):
            mark_faq_completeness(response.content, parsed, str(response.url))
        mark_missing_attachment(row["url"], media, parsed, str(response.url))
        if upgraded:
            parsed.flags.append("source_http_link_retrieved_over_https")
        return {"body": response.content, "media_type": media, "parsed": parsed,
                "final_url": str(response.url), "headers": response.headers}
    except RateLimited as exc:
        return {"deferred_until": exc.retry_at, "error": str(exc), "attempted": exc.attempted}
    except Exception as exc:
        return {"error": type(exc).__name__+": "+str(exc)[:1000],
                "blocked": isinstance(exc, (PermissionError, ValueError)),
                "http_status": exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None}
    finally:
        client.close()


def cache_eu_source(factory, doc_id, transaction=None):
    """The SEDIA catalogue already carries full display metadata in its detailed variant."""
    with (nullcontext(transaction) if transaction is not None else factory.begin()) as session:
        doc = session.get(Document, doc_id)
        item = session.scalar(select(SourceItem).join(OpportunityDocument,
            SourceItem.opportunity_id == OpportunityDocument.opportunity_id
        ).where(OpportunityDocument.document_id == doc_id, SourceItem.source_id == "eu-funding"))
        if item is None:
            raise ValueError("EU source entry missing")
        body = item.raw_json.encode("utf-8")
        try:
            raw = json.loads(body)
            parsed = parse_document(body, "application/json", doc.url, "eu_json")
        except Exception as exc:
            raw = {}
            parsed = Parsed(status="unreadable", flags=["parser_error:"+type(exc).__name__+":"+str(exc)[:300]])
        parsed.flags.append("source_api_entries_serialized_from_catalogue")
        mark_eu_completeness(raw, parsed, doc.url)
        persist(session, doc, body, "application/json", parsed, stamp=item.last_seen_at)
        # Prevent immediate reprocessing if a stale catalogue is being enriched.
        doc.next_check_at = next_daily_check(now())


def coverage(factory):
    from sqlalchemy import text
    with factory() as session:
        faq = session.scalar(select(Document).where(Document.parser == "eu_faq_catalogue").limit(1))
        current = select(OpportunityDocument.document_id).where(OpportunityDocument.active == True,  # noqa: E712
                                                               OpportunityDocument.limitation.is_(None))
        return {
            "calls": dict(session.execute(text("SELECT content_state,COUNT(*) FROM v_funding GROUP BY content_state")).all()),
            "documents": dict(session.execute(select(Document.state, func.count()).group_by(Document.state)).all()),
            "current_documents": dict(session.execute(select(Document.state, func.count()).where(
                Document.id.in_(current)).group_by(Document.state)).all()),
            "originals": session.scalar(select(func.count()).select_from(DocumentBlob)),
            "faq_catalogue": {"state": faq.state, "checked_at": faq.checked_at, "error": faq.error} if faq else {"state": "not_started"},
            "complete_universe_claimed": False,
            "note": "collected_unverified means discovered documentary links collected; expert completeness check still required",
        }


def enrich_documents(factory, cfg, source_ids=None, workers=6, max_fetches=0, max_depth=4, max_documents=250,
                     retry_failed=False, client_factory=DocumentClient, pending_only=False, current_only=False):
    owner = str(uuid4())
    if not acquire(factory, "collector", owner):
        raise RuntimeError("Another collector owns the database lease")
    count = 0
    run_started = now()
    try:
        ids = seed(factory, source_ids, current_only, run_started)
        with factory() as session:
            known_documents = set(session.scalars(select(Document.id)))
            for error in session.scalars(select(Document.error).where(Document.error.like("RATE_LIMIT|%"),
                                                                       Document.next_check_at > run_started)):
                _, origin, stamp = error.split("|", 2)
                PublicClient.defer_origin(origin, datetime.fromisoformat(stamp))
        print(dump({"stage": "expanding_document_references", "opportunities": len(ids)}), flush=True)
        refresh_graph(factory, ids, max_depth, max_documents, known_documents, owner)
        if retry_failed:
            with factory.begin() as session:
                eligible = select(OpportunityDocument.document_id).join(
                    Opportunity, Opportunity.id == OpportunityDocument.opportunity_id
                ).where(OpportunityDocument.active == True, OpportunityDocument.limitation.is_(None))  # noqa: E712
                if source_ids:
                    eligible = eligible.where(Opportunity.source_id.in_(source_ids))
                if current_only:
                    eligible = eligible.where(current_opportunities(run_started))
                session.execute(update(Document).where(Document.id.in_(eligible),
                    Document.state.in_(("failed", "blocked"))).values(next_check_at=None))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pending, last_report = {}, 0.0
            candidates, dirty_documents = deque(), set()
            last_expansion = time.monotonic()
            while True:
                capacity = workers*2-len(pending)
                if max_fetches:
                    capacity = min(capacity, max_fetches-count-len(pending))
                active = and_(Opportunity.source_status.in_(("open", "forthcoming", "rolling")),
                              current_opportunities(run_started))
                priority = select(OpportunityDocument.document_id,
                    func.min(case((active, 0), (Opportunity.source_status == "unknown", 1), else_=2)).label("priority"),
                    func.min(OpportunityDocument.depth).label("depth")).join(
                    Opportunity, Opportunity.id == OpportunityDocument.opportunity_id
                ).where(OpportunityDocument.active == True, OpportunityDocument.limitation.is_(None))  # noqa: E712
                if source_ids:
                    priority = priority.where(Opportunity.source_id.in_(source_ids))
                if current_only:
                    priority = priority.where(current_opportunities(run_started))
                priority = priority.group_by(OpportunityDocument.document_id).subquery()
                selected = []
                with factory() as session:
                    if capacity > 0 and not candidates:
                        stmt = select(Document).join(priority, priority.c.document_id == Document.id).where(
                            or_(Document.next_check_at.is_(None), Document.next_check_at <= run_started),
                            Document.id.not_in(list(pending.values()))
                        ).order_by(priority.c.priority, priority.c.depth, Document.id).limit(500)
                        if pending_only:
                            stmt = stmt.where(Document.state.in_(("pending", "failed", "blocked") if retry_failed else ("pending",)))
                        candidates.extend({c.name: getattr(d, c.name) for c in Document.__table__.columns}
                                          for d in session.scalars(stmt))
                for _ in range(min(capacity, len(candidates))):
                    selected.append(candidates.popleft())
                completed_ids = []
                eu_rows = [row for row in selected if row["parser"] == "eu_source"]
                if eu_rows:
                    with factory.begin() as session:
                        heartbeat(session, owner)
                        for row in eu_rows:
                            cache_eu_source(factory, row["id"], session)
                            count += 1
                            completed_ids.append(row["id"])
                for row in selected:
                    if row["parser"] != "eu_source":
                        pending[pool.submit(fetch_document, cfg, row, client_factory)] = row["id"]
                if not pending and not completed_ids:
                    if dirty_documents:
                        with factory() as session:
                            affected = list(session.scalars(select(OpportunityDocument.opportunity_id).where(
                                OpportunityDocument.document_id.in_(dirty_documents),
                                OpportunityDocument.active == True).distinct()))  # noqa: E712
                        refresh_graph(factory, affected, max_depth, max_documents, known_documents, owner)
                        dirty_documents.clear()
                        if not max_fetches or count < max_fetches:
                            continue
                    break
                done = wait(pending, timeout=0 if completed_ids else 30, return_when=FIRST_COMPLETED).done if pending else set()
                for future in done:
                    did, result = pending.pop(future), future.result()
                    with factory.begin() as session:
                        heartbeat(session, owner)
                        doc = session.get(Document, did)
                        if "deferred_until" in result:
                            doc.state, doc.error = "pending", result["error"]
                            doc.next_check_at = result["deferred_until"]
                            if result["attempted"]:
                                doc.checked_at, doc.http_status = now(), 429
                                doc.attempts += 1
                        elif "error" in result:
                            doc.state = "blocked" if result["blocked"] else "failed"
                            doc.error, doc.http_status = result["error"], result["http_status"]
                            doc.checked_at, doc.next_check_at = now(), next_daily_check(now())
                            doc.attempts += 1
                        elif result.get("not_modified"):
                            if doc.current_sha256 is None:
                                raise ValueError("304 received without a cached original")
                            doc.state, doc.checked_at, doc.last_success_at = "fetched", now(), now()
                            doc.next_check_at, doc.error = next_daily_check(now()), None
                            media = session.get(DocumentBlob, doc.current_sha256).media_type
                            issue = document_response_issue(doc.url, media, doc.final_url)
                            if issue:
                                doc.error, doc.extraction_status = issue, "unreadable"
                            doc.http_status, doc.attempts = 304, doc.attempts+1
                            session.get(DocumentVersion, (doc.id, doc.current_sha256)).last_seen_at = now()
                        else:
                            persist(session, doc, **result)
                    count += 1
                    completed_ids.append(did)
                with factory.begin() as session:
                    heartbeat(session, owner)
                # Batch shared references: a single EU guide may belong to thousands of calls.
                dirty_documents.update(completed_ids)
                if dirty_documents and (len(dirty_documents) >= 500 or time.monotonic()-last_expansion >= 300):
                    with factory() as session:
                        affected = list(session.scalars(select(OpportunityDocument.opportunity_id).where(
                            OpportunityDocument.document_id.in_(dirty_documents), OpportunityDocument.active == True  # noqa: E712
                        ).distinct()))
                    refresh_graph(factory, affected, max_depth, max_documents, known_documents, owner)
                    dirty_documents.clear()
                    # A new source version may have made queued links inactive.
                    candidates.clear()
                    last_expansion = time.monotonic()
                if time.monotonic()-last_report >= 30:
                    print(dump({"processed": count, "utc": now(), "in_flight": len(pending)}), flush=True)
                    last_report = time.monotonic()
        print(dump(coverage(factory)), flush=True)
        return coverage(factory)
    finally:
        with factory.begin() as session:
            session.execute(delete(Lease).where(Lease.name == "collector", Lease.owner == owner))


def reextract_documents(factory, parsers=None, issues_only=False, document_ids=None):
    """Rebuild derivatives from archived bytes without changing source observation dates."""
    owner = str(uuid4())
    if not acquire(factory, "collector", owner):
        raise RuntimeError("Another collector owns the database lease")
    try:
        with factory() as session:
            stmt = select(Document.id).where(Document.current_sha256.is_not(None))
            if parsers:
                stmt = stmt.where(Document.parser.in_(parsers))
            if issues_only:
                stmt = stmt.where(Document.extraction_status != "extracted")
            ids = list(session.scalars(stmt))
            if document_ids is not None:
                requested = set(document_ids)
                ids = [did for did in ids if did in requested]
        changed = 0
        for i, did in enumerate(ids):
            with factory.begin() as session:
                heartbeat(session, owner)
                doc = session.get(Document, did)
                blob = session.get(DocumentBlob, doc.current_sha256)
                body = gzip.decompress(blob.original_gzip)
                media = infer_media_type(body, blob.media_type)
                mode = "eu_json" if doc.parser.startswith("eu_") else doc.parser
                try:
                    parsed = parse_document(body, media, doc.final_url or doc.url, mode)
                except Exception as exc:
                    parsed = Parsed(status="unreadable", flags=["parser_error:"+str(exc)[:300]])
                for flag in json.loads(blob.flags_json):
                    if flag.startswith(("source_api_", "source_http_", "catalogue_document_id:", "public_post_query:", "collection_manifest_")):
                        if flag not in parsed.flags:
                            parsed.flags.append(flag)
                if doc.parser == "eu_source":
                    mark_eu_completeness(body, parsed, doc.final_url or doc.url)
                if doc.parser in ("eu_faq_source", "eu_faq_detail"):
                    mark_faq_completeness(body, parsed, doc.final_url or doc.url)
                mark_missing_attachment(doc.url, media, parsed, doc.final_url)
                changed += persist(session, doc, body, media, parsed, stamp=doc.last_success_at,
                                   preserve_observation=True)
            if (i+1) % 25 == 0:
                print(dump({"reextracted": i+1, "total": len(ids), "changed": changed}), flush=True)
        affected = set()
        for start in range(0, len(ids), 500):
            with factory() as session:
                affected.update(session.scalars(select(OpportunityDocument.opportunity_id).where(
                    OpportunityDocument.document_id.in_(ids[start:start+500]),
                    OpportunityDocument.active == True).distinct()))  # noqa: E712
        refresh_graph(factory, list(affected), owner=owner)
        return {"reextracted": len(ids), "changed": changed}
    finally:
        with factory.begin() as session:
            session.execute(delete(Lease).where(Lease.name == "collector", Lease.owner == owner))
