"""Create a consistent SQLite snapshot and open-format extracts for the delivery."""
import hashlib
import json
import sqlite3
from pathlib import Path

from sqlalchemy import select

from funding.api import create_app
from funding.db import make_engine, sessions
from funding.documents import coverage
from funding.domain import dump, now
from funding.export import export_data
from funding.models import Opportunity, Tag
from funding.priorities import load_priorities, priority_directory, priority_predicate
from funding.query import funder_directory, funding_view, health
from funding.settings import Settings
from funding.views import STATUS_SQL

out = Path("outputs/data")
out.mkdir(parents=True, exist_ok=True)
with sqlite3.connect("data/funding.db") as source, sqlite3.connect(out/"funding.db") as target:
    if source.execute("SELECT count(*) FROM leases WHERE expires_at > datetime('now')").fetchone()[0]:
        raise RuntimeError("Stop the collector before producing delivery files")
    source.backup(target)
    captured_at = now()
    transport_labels_normalized = 0
    for sha, flags_json in target.execute("SELECT sha256,flags_json FROM document_blobs WHERE flags_json LIKE '%source_http_link_retrieved_over_https%'").fetchall():
        flags = [flag for flag in json.loads(flags_json) if flag != "source_http_link_retrieved_over_https"]
        target.execute("UPDATE document_blobs SET flags_json=? WHERE sha256=?", (dump(flags), sha))
        transport_labels_normalized += 1
    target.commit()
    assert target.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert target.execute("PRAGMA foreign_key_check").fetchall() == []
source.close()
target.close()
print(dump({"stage": "snapshot_ready", "captured_at_utc": captured_at}), flush=True)
cfg = Settings(database_url=f"sqlite:///{out}/funding.db")
engine = make_engine(cfg)
factory = sessions(engine)
export_data(engine, factory, out)
with engine.connect() as conn:
    rows = [dict(r) for r in conn.execute(select(funding_view(engine))).mappings()]
    tags = {}
    for tag in conn.execute(select(Tag.__table__)).mappings():
        tags.setdefault(tag["opportunity_id"], {}).setdefault(tag["kind"], []).append(tag["value"])
    priority_definitions = load_priorities(cfg.priority_file)
    memberships = {}
    for priority in priority_definitions:
        for oid in conn.scalars(select(Opportunity.id).where(priority_predicate(Opportunity.__table__, priority))):
            memberships.setdefault(oid, []).append(priority["id"])
for row in rows:
    row["themes"] = ", ".join(tags.get(row["id"], {}).get("theme", []))
    row["regions"] = ", ".join(tags.get(row["id"], {}).get("region", []))
    row["priorities"] = memberships.get(row["id"], [])
    row["cascade"] = row["source_id"] == "eu-funding" and row["external_id"].startswith("cascade:")
sources = health(factory)
priorities = priority_directory(engine, funding_view(engine), sources, priority_definitions)
(out/"priorities.json").write_text(dump(priorities)+"\n", encoding="utf-8")
(out/"priority-memberships.jsonl").write_text("".join(dump({"opportunity_id": oid, "priority_id": pid})+"\n"
    for oid, values in sorted(memberships.items()) for pid in values), encoding="utf-8")
funders = funder_directory(engine)
document_coverage = coverage(factory)
data = {"created_at_utc": captured_at, "rows": rows, "sources": sources, "funders": funders, "document_coverage": document_coverage, "priorities": priorities["items"]}
(out/"funders.json").write_text(dump(funders)+"\n", encoding="utf-8")
Path("tmp").mkdir(exist_ok=True)
Path("tmp/workbook-data.json").write_text(dump(data), encoding="utf-8")
Path("integrations/openapi.json").write_text(json.dumps(create_app(cfg, engine).openapi(), ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
engine.dispose()
with sqlite3.connect(out/"funding.db") as conn:
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.execute("PRAGMA journal_mode=DELETE")
    status_sql = STATUS_SQL.replace("CAST(CURRENT_TIMESTAMP AS DATE)", "DATE(CURRENT_TIMESTAMP)")
    metrics = {
        "as_of_utc": str(captured_at),
        "transport_labels_normalized": transport_labels_normalized,
        "opportunities": len(rows),
        "by_source": dict(conn.execute("SELECT source_id,count(*) FROM opportunities GROUP BY source_id")),
        "by_status": dict(conn.execute("SELECT effective_status,count(*) FROM v_funding GROUP BY effective_status")),
        "by_record_kind": dict(conn.execute("SELECT record_kind,count(*) FROM opportunities GROUP BY record_kind")),
        "funder_names": len(funders),
        "structured_sources": sum(s["collection_level"] == "structured" for s in sources),
        "raw_eu_documents": conn.execute("SELECT sum(json_array_length(raw_json,'$.documents')) FROM source_items WHERE source_id='eu-funding'").fetchone()[0],
        "source_count": len(sources),
        "document_coverage": document_coverage,
        "document_formats": [dict(zip(("media_type", "originals", "original_bytes", "pages"), row, strict=True))
                             for row in conn.execute("SELECT media_type,count(*),sum(byte_count),sum(page_count) FROM document_blobs GROUP BY media_type")],
        "documents_by_parser_state": [dict(zip(("parser", "state", "documents"), row, strict=True))
                                      for row in conn.execute("SELECT parser,state,count(*) FROM documents GROUP BY parser,state")],
        "text_extraction": dict(conn.execute("SELECT extraction_status,count(*) FROM document_blobs GROUP BY extraction_status")),
        "opportunities_with_faq": conn.execute("SELECT count(distinct opportunity_id) FROM opportunity_documents WHERE active=1 AND role='faq_keyword_match'").fetchone()[0],
        "source_content_gaps": {
            "current_or_unknown_pending_documents": conn.execute(
                "SELECT count(DISTINCT d.id) FROM documents d JOIN opportunity_documents od ON od.document_id=d.id "
                "JOIN opportunities o ON o.id=od.opportunity_id WHERE od.active=1 AND od.limitation IS NULL "
                "AND d.state='pending' AND ("+status_sql+") NOT IN ('closed','cancelled')").fetchone()[0],
            "attachment_urls_returning_html": conn.execute("SELECT count(*) FROM documents WHERE error='DOCUMENT_DOWNLOAD_RETURNED_HTML'").fetchone()[0],
            "details_redirecting_to_front_pages": conn.execute("SELECT count(*) FROM documents WHERE error='DETAIL_REDIRECTED_TO_FRONT_PAGE'").fetchone()[0],
            "rate_limit_deferred_documents": conn.execute("SELECT count(*) FROM documents WHERE state='pending' AND error LIKE 'RATE_LIMIT|%'").fetchone()[0],
            "eu_entries_without_published_body": conn.execute("SELECT count(*) FROM documents d JOIN document_blobs b ON b.sha256=d.current_sha256 WHERE d.parser='eu_source' AND b.flags_json LIKE '%full_eu_conditions_not_present_in_source_entry%'").fetchone()[0],
            "faq_entries_without_published_question_or_answer": conn.execute("SELECT count(*) FROM documents d JOIN document_blobs b ON b.sha256=d.current_sha256 WHERE d.parser='eu_faq_source' AND b.flags_json LIKE '%full_faq_question_or_answer_not_published%'").fetchone()[0],
        },
        "completeness_verified": False,
        "source_issues": [{"id": s["id"], "error": s["last_error"]} for s in sources if s["enabled"] and s["health"] != "success"],
        "table_counts": {name: conn.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0] for name, in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()},
        "sqlite_integrity_check": "ok", "sqlite_foreign_key_check": "ok",
    }
metrics["database_sha256"] = hashlib.file_digest((out/"funding.db").open("rb"), "sha256").hexdigest()
(out/"metrics.json").write_text(dump(metrics)+"\n", encoding="utf-8")
print(dump(metrics))
