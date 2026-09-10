from fastapi.testclient import TestClient
from sqlalchemy import select

from funding.api import create_app
from funding.collector import acquire, upsert
from funding.db import make_engine
from funding.document_parsers import Parsed
from funding.documents import associate, ensure_document, persist
from funding.domain import Record, opportunity_id
from funding.export import transfer_database
from funding.models import Base
from funding.settings import Settings
from funding.views import view_statements


def empty_target(tmp_path):
    target = make_engine(Settings(database_url=f"sqlite:///{tmp_path}/destination.db"))
    Base.metadata.create_all(target)
    with target.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32))")
        conn.exec_driver_sql("INSERT INTO alembic_version VALUES ('0001')")
        for statement in view_statements("sqlite"):
            conn.exec_driver_sql(statement)
    return target


def test_transfer_preserves_relations_source_data_and_review_history(database, tmp_path):
    cfg, source, factory = database
    record = Record(external_id="transfer-1", canonical_url="https://example.org/transfer", title="Ääkköset ja yhteistyö", total_budget="1234567.89")
    with factory.begin() as s:
        upsert(s, "test", record, {"source": "Täysi alkuperäinen aineisto", "nullable": None})
        doc = ensure_document(s, "https://example.org/terms.bin")
        associate(s, opportunity_id(record.canonical_url), doc, root=True)
        persist(s, doc, bytes(range(256))*256, "application/octet-stream", Parsed(text="Täydet ehdot. "*5000))
    client = TestClient(create_app(cfg, source))
    result = client.put(f"/v1/opportunities/{opportunity_id(record.canonical_url)}/review", json={"expected_version": 0, "source_version": 2, "eligibility": "conditional", "evidence_url": record.canonical_url, "notes": "Kumppanina"})
    assert result.status_code == 200
    target = empty_target(tmp_path)
    transfer_database(source, target)
    with source.connect() as a, target.connect() as b:
        for table in Base.metadata.sorted_tables:
            assert list(a.execute(select(table)).mappings()) == list(b.execute(select(table)).mappings())
        assert b.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    target.dispose()


def test_transfer_refuses_while_collector_is_active(database, tmp_path):
    import pytest
    _, source, factory = database
    assert acquire(factory, "collector", "in-progress")
    target = empty_target(tmp_path)
    with pytest.raises(ValueError, match="Stop the active collector"):
        transfer_database(source, target)
    target.dispose()
