"""Public SEDIA FAQ catalogue, with exact topic-keyword associations and full answers."""
import json
from pathlib import Path

from sqlalchemy import select

from funding.adapters import first
from funding.document_parsers import parse_document
from funding.documents import associate, ensure_document, mark_faq_completeness, next_daily_check, persist
from funding.domain import dump, now
from funding.http import PublicClient
from funding.models import Change, Document, Lease, Opportunity, OpportunityDocument

API = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"


def fetch_faq_pages(cfg, directory, client_factory=PublicClient, topic_ids=None, progress=None):
    if topic_ids is None:
        from funding.db import make_engine
        engine = make_engine(cfg)
        with engine.connect() as conn:
            topic_ids = list(conn.scalars(select(Opportunity.external_id).where(Opportunity.source_id == "eu-funding")))
        engine.dispose()
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    client = client_factory(cfg, ["api.tech.ec.europa.eu"])
    seen, pages, warnings = set(), [], []
    expected_total = 0
    base = [{"term": {"language": "en"}}, {"terms": {"keyword": sorted(set(topic_ids))}}]

    def request(extra, page):
        query = {"bool": {"must": base+extra}}
        url = f"{API}?apiKey=SEDIA_FAQ&text=***&pageSize=100&pageNumber={page}"
        response = client.request("POST", url, files={
            "query": ("query.json", dump(query), "application/json"),
            "languages": ("languages.json", '["en"]', "application/json"),
        })
        if progress:
            progress()
        return response, url, query

    def partition(extra, lower, upper, depth=0):
        nonlocal expected_total
        response, url, query = request(extra, 1)
        first_data = response.json()
        total = int(first_data["totalResults"])
        if total >= 9000:
            if depth >= 24 or upper-lower < 2:
                raise ValueError("FAQ partition exceeds API window; finer partition required")
            middle = (lower+upper)//2
            before = expected_total
            partition(extra+[{"range": {"publicationDate": {"lt": str(middle)}}}], lower, middle, depth+1)
            partition(extra+[{"range": {"publicationDate": {"gte": str(middle)}}}], middle, upper, depth+1)
            if expected_total-before != total:
                warnings.append(f"partition_total_mismatch:{total}:{expected_total-before}")
            return
        expected_total += total
        fetched, page = 0, 1
        while True:
            if page > 1:
                response, url, query = request(extra, page)
            data = response.json()
            if int(data["totalResults"]) != total:
                warnings.append(f"source_total_changed:{total}:{data['totalResults']}")
            for row in data["results"]:
                ref = row["reference"]
                if ref in seen:
                    warnings.append("duplicate_reference:"+str(ref))
                if first(row["metadata"], "language") != "en":
                    raise ValueError("FAQ language filter drifted")
                seen.add(ref)
            filename = f"partition-page-{len(pages)+1:04d}.json"
            (directory/filename).write_bytes(response.content)
            pages.append({"file": filename, "url": url, "checked_at": str(now()), "request": query})
            fetched += len(data["results"])
            print(dump({"faq_pages": len(pages), "unique": len(seen), "partition_fetched": fetched, "partition_expected": total}), flush=True)
            if fetched >= total:
                if fetched != total:
                    warnings.append(f"partition_count_mismatch:{fetched}:{total}")
                break
            if not data["results"] or page >= 90:
                raise ValueError("FAQ partition truncated before its advertised end")
            page += 1
    try:
        if topic_ids:
            partition([{"exists": {"field": "publicationDate"}}], -2208988800000, 10413792000000)
            partition([{"bool": {"must_not": [{"exists": {"field": "publicationDate"}}]}}], -2208988800000, 10413792000000)
        if len(seen) != expected_total:
            warnings.append(f"unique_count_mismatch:{len(seen)}:{expected_total}")
        manifest = {"pages": pages, "expected": expected_total, "unique_entries": len(seen), "language": "en",
                    "topic_count": len(topic_ids), "topic_ids": sorted(set(topic_ids)),
                    "scope": "exact topic keywords, as used by the public topic Q&A view",
                    "warnings": sorted(set(warnings)), "completed_at": str(now())}
        (directory/"manifest.json").write_text(dump(manifest)+"\n", encoding="utf-8")
        return manifest
    finally:
        client.close()


def import_faq_pages(factory, directory, progress=None):
    from datetime import datetime
    directory = Path(directory)
    manifest = json.loads((directory/"manifest.json").read_text(encoding="utf-8"))
    with factory() as session:
        topics = {ext.upper(): oid for oid, ext in session.execute(select(
            Opportunity.id, Opportunity.external_id).where(Opportunity.source_id == "eu-funding"))}
    count, matched, seen, current_associations = 0, set(), set(), set()
    for page in manifest["pages"]:
        body = (directory/page["file"]).read_bytes()
        data = json.loads(body)
        with factory.begin() as session:
            parent = ensure_document(session, page["url"], "eu_faq_index", "EU FAQ catalogue (English)", request_identity=dump(page["request"]))
            parsed = parse_document(body, "application/json", page["url"], "eu_json")
            parsed.flags.append("public_post_query:"+dump(page["request"]))
            persist(session, parent, body, "application/json", parsed, stamp=datetime.fromisoformat(page["checked_at"]))
            for row in data["results"]:
                if row["reference"] in seen:
                    continue
                seen.add(row["reference"])
                meta = row["metadata"]
                url = first(meta, "url") or row["url"]
                doc = ensure_document(session, url, "eu_faq_source", first(meta, "question"))
                entry = dump(row).encode("utf-8")
                parsed = parse_document(entry, "application/json", url, "eu_json")
                parsed.flags.append("source_api_entry_serialized_from_faq_catalogue")
                parsed.flags.append("catalogue_document_id:"+parent.id)
                mark_faq_completeness(row, parsed, url)
                for keyword in meta.get("keyword", []):
                    oid = topics.get(keyword.strip().upper())
                    if oid:
                        associate(session, oid, doc, role="faq_keyword_match", root=True)
                        matched.add(oid)
                        current_associations.add((oid, doc.id))
                persist(session, doc, entry, "application/json", parsed, stamp=datetime.fromisoformat(page["checked_at"]))
                doc.next_check_at = next_daily_check(now())
                count += 1
        if progress:
            progress()
    if count != manifest.get("unique_entries", manifest["expected"]):
        raise ValueError("FAQ snapshot count does not match manifest")
    # A verified complete refresh may retire old keyword associations, never their history.
    if not manifest.get("warnings") and {x.upper() for x in manifest.get("topic_ids", [])} == set(topics):
        from funding.transactions import lock_change_log
        with factory.begin() as session:
            stale = [m for m in session.scalars(select(OpportunityDocument).where(
                OpportunityDocument.role == "faq_keyword_match", OpportunityDocument.is_root == True))  # noqa: E712
                if (m.opportunity_id, m.document_id) not in current_associations]
            if stale:
                lock_change_log(session)
            for mapping in stale:
                mapping.is_root, mapping.active = False, False
                opportunity = session.get(Opportunity, mapping.opportunity_id)
                opportunity.version += 1
                opportunity.updated_at = now()
                session.add(Change(opportunity_id=opportunity.id, source_id=opportunity.source_id,
                    kind="document_unlinked", created_at=now(), actor="faq_collector",
                    payload_json=dump({"document_id": mapping.document_id, "reason": "FAQ keyword no longer published"})))
    print(dump({"faq_entries": count, "topics_with_exact_faq_keyword": len(matched)}), flush=True)
    return {"faq_entries": count, "matched_opportunities": len(matched)}


def collect_faq(factory, cfg, from_directory=None):
    from tempfile import TemporaryDirectory
    from uuid import uuid4

    from sqlalchemy import delete

    from funding.collector import acquire, heartbeat
    from funding.domain import digest
    owner = str(uuid4())
    index_url = f"{API}?apiKey=SEDIA_FAQ"
    if not acquire(factory, "collector", owner):
        raise RuntimeError("Another collector owns the database lease")
    try:
        def renew():
            with factory.begin() as session:
                heartbeat(session, owner)
        with factory.begin() as session:
            doc = ensure_document(session, index_url, "eu_faq_catalogue", "EU FAQ collection manifest")
            if not from_directory and doc.state == "fetched" and doc.checked_at and doc.checked_at.date() == now().date():
                return {"status": "cached", "checked_at": doc.checked_at}
            doc.state, doc.error = "pending", None
        with TemporaryDirectory(prefix="funding-faq-") as temp:
            directory = Path(from_directory or temp)
            if not from_directory:
                fetch_faq_pages(cfg, directory, progress=renew)
            with factory.begin() as session:
                heartbeat(session, owner)
            result = import_faq_pages(factory, directory, progress=renew)
            manifest_body = (directory/"manifest.json").read_bytes()
            warnings = json.loads(manifest_body).get("warnings", [])
        with factory.begin() as session:
            doc = session.get(Document, digest(index_url))
            parsed = parse_document(manifest_body, "application/json", index_url, "eu_json")
            parsed.flags.append("collection_manifest_not_a_funder_document")
            persist(session, doc, manifest_body, "application/json", parsed)
            if warnings:
                doc.state, doc.error = "failed", "FAQ catalogue changed during pagination: "+dump(warnings)[:2000]
            return {**result, "status": "partial" if warnings else "success", "warnings": warnings}
    except Exception as exc:
        with factory.begin() as session:
            doc = session.get(Document, digest(index_url))
            if doc:
                doc.state, doc.error, doc.checked_at = "failed", str(exc)[:2000], now()
        raise
    finally:
        with factory.begin() as session:
            session.execute(delete(Lease).where(Lease.name == "collector", Lease.owner == owner))


if __name__ == "__main__":
    import sys

    from funding.settings import settings
    fetch_faq_pages(settings(), sys.argv[1] if len(sys.argv) > 1 else "tmp/eu-faq")
