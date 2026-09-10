import json

from sqlalchemy import select

from funding.collector import upsert
from funding.documents import refresh_graph
from funding.domain import Record, dump, opportunity_id
from funding.eu_faq import import_faq_pages
from funding.models import Document, OpportunityDocument, Source


def test_complete_faq_refresh_retires_removed_association_and_preserves_history(database, tmp_path):
    _, _, factory = database
    record = Record(external_id="TOPIC-1", canonical_url="https://example.org/topic", title="Test call")
    oid = opportunity_id(record.canonical_url)
    with factory.begin() as session:
        session.add(Source(id="eu-funding", name="EU", url="https://example.org", adapter="eu", category="eu",
                           coverage="test", owner="test", enabled=True, config_json="{}"))
        session.flush()
        upsert(session, "eu-funding", record, {})
    row = {"reference": "FAQ-1", "url": "https://example.org/faq/1", "metadata": {
        "url": ["https://example.org/faq/1"], "question": ["Can cities apply?"],
        "answer": ["Complete answer with conditions. "*3000], "keyword": ["topic-1"]}}
    def snapshot(rows, warnings=None):
        (tmp_path/"page.json").write_text(dump({"totalResults": len(rows), "results": rows}), encoding="utf-8")
        (tmp_path/"manifest.json").write_text(json.dumps({
            "pages": [{"file": "page.json", "url": "https://example.org/faq-index", "request": {},
                       "checked_at": "2026-01-01 12:00:00"}], "expected": len(rows), "unique_entries": len(rows),
            "topic_ids": ["TOPIC-1"], "warnings": warnings or []}), encoding="utf-8")
        return import_faq_pages(factory, tmp_path)
    assert snapshot([row])["matched_opportunities"] == 1
    with factory() as session:
        mapping = session.scalar(select(OpportunityDocument).where(OpportunityDocument.opportunity_id == oid))
        assert mapping.active and mapping.is_root
        did = mapping.document_id
    snapshot([], ["source_total_changed"])
    with factory() as session:
        assert session.get(OpportunityDocument, (oid, did)).is_root
    snapshot([])
    refresh_graph(factory, [oid])
    with factory() as session:
        mapping = session.get(OpportunityDocument, (oid, did))
        assert not mapping.active and not mapping.is_root
        assert session.get(Document, did).current_sha256 is not None
