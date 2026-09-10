"""Integration test inside the release container, against a disposable SQL Server."""
import gzip
import os
import time
from decimal import Decimal

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import URL

from funding.api import create_app
from funding.collector import sync_sources, upsert
from funding.db import make_engine, sessions
from funding.document_parsers import Parsed
from funding.documents import associate, current_opportunities, ensure_document, persist
from funding.domain import Record, due, now, opportunity_id
from funding.export import transfer_database
from funding.models import Change, DocumentBlob, Opportunity
from funding.settings import Settings

password = os.environ["MSSQL_SA_PASSWORD"]
url = URL.create("mssql+pyodbc", username="sa", password=password, host=os.environ.get("FUNDING_TEST_SQL_HOST", "funding-test-sql"), database="master", query={"driver": "ODBC Driver 18 for SQL Server", "Encrypt": "yes", "TrustServerCertificate": "yes"})
master = create_engine(url, isolation_level="AUTOCOMMIT", connect_args={"timeout": 5})
for attempt in range(12):
    try:
        with master.connect() as conn:
            conn.execute(text("SELECT 1"))
        break
    except Exception as exc:
        if attempt == 0:
            print("SQL connection retry:", str(getattr(exc, "orig", exc)).replace(password, "[redacted]")[:500], flush=True)
        if attempt == 11:
            raise RuntimeError("SQL Server did not become ready") from None
        time.sleep(3)
with master.connect() as conn:
    conn.execute(text("CREATE DATABASE fundingtest"))
    conn.execute(text("CREATE DATABASE fundingtransfer"))


def migrate(connection_url):
    os.environ["FUNDING_DATABASE_URL"] = connection_url
    command.upgrade(Config("alembic.ini"), "head")
    return make_engine(Settings(database_url=connection_url))


engine = migrate(url.set(database="fundingtest").render_as_string(hide_password=False))
factory = sessions(engine)
sync_sources(factory, Settings().source_file)
record = Record(external_id="TEST-1", canonical_url="https://example.org/sql-test", title="Ääkköset ja ilmasto", deadlines=[due("2020-01-01T12:00:00Z")], source_status="open", total_budget=Decimal("1234567.89"))
with factory.begin() as session:
    assert upsert(session, "manual", record, {"original": "test"})
with factory.begin() as session:
    assert not upsert(session, "manual", record, {"original": "test"})
with factory() as session:
    assert session.scalar(select(func.count()).select_from(Opportunity)) == 1
    assert session.scalar(select(func.count()).select_from(Change)) == 1
client = TestClient(create_app(Settings(auth_mode="local"), engine))
assert client.get("/v1/opportunities?status=closed&limit=1&offset=0").json()["total"] == 1
assert client.get("/v1/opportunities?q=ääkköset").json()["total"] == 1
oid = opportunity_id(record.canonical_url)
body = b"Archived source bytes\x00"*5000
full_text = "Täydelliset ehdot ja ääkköset. "*4000+"Viimeinen ehto: omarahoitus 20 %."
with factory.begin() as session:
    doc = ensure_document(session, "https://example.org/rules")
    associate(session, oid, doc, root=True)
    persist(session, doc, body, "application/octet-stream", Parsed(text=full_text))
    document_id = doc.id
assert client.get("/v1/opportunities?content_q=omarahoitus").json()["total"] == 1
assert client.get(f"/v1/documents/{document_id}/original").content == body
assert client.get(f"/v1/documents/{document_id}/text").json()["full_text"] == full_text
with factory.begin() as session:
    landing_body = b"<main>Shared public front page</main>"
    missing = ensure_document(session, "https://example.org/missing.pdf")
    persist(session, missing, landing_body, "text/html", Parsed(text="First extraction"))
    valid = ensure_document(session, "https://example.org")
    persist(session, valid, landing_body, "text/html", Parsed(text="Corrected extraction"))
    session.refresh(missing)
    assert missing.error == "DOCUMENT_DOWNLOAD_RETURNED_HTML" and missing.extraction_status == "unreadable"
    assert valid.extraction_status == "extracted" and valid.error is None
review = dict(expected_version=0, source_version=2, eligibility="conditional", evidence_url="https://example.org/rules", notes="Säilyvä arvio")
assert client.put(f"/v1/opportunities/{oid}/review", json=review).status_code == 200
assert client.put(f"/v1/opportunities/{oid}/review", json=review).status_code == 409
assert client.get("/v1/changes?limit=1").json()["has_more"]
with factory() as session:
    assert session.scalar(select(func.count()).select_from(Opportunity).where(current_opportunities(now()))) == 0
with factory.begin() as session:
    upsert(session, "manual", Record(external_id="TEST-SCHEME", canonical_url="https://example.org/scheme",
        title="Pysyvä rahoitusmuoto", record_kind="funding_scheme"), {})
with factory() as session:
    assert session.scalar(select(func.count()).select_from(Opportunity).where(current_opportunities(now()))) == 1
with factory.begin() as session:
    upsert(session, "eu-funding", Record(external_id="cascade:42", canonical_url="https://example.org/cascade",
        title="FSTP SQL test"), {})
    upsert(session, "pirkanmaa-myr", Record(external_id="MYR-TEST", canonical_url="https://example.org/myr",
        title="MYR ennakkotieto", record_kind="advance_information", instrument="other"), {})
assert client.get("/v1/opportunities?cascade=true").json()["total"] == 1
assert client.get("/v1/opportunities?priority=1").json()["total"] == 1
assert client.get("/v1/opportunities?priority=4&record_kind=advance_information").json()["total"] == 1
assert client.get("/v1/priorities").json()["items"][3]["advance_information"] == 1

sqlite = migrate("sqlite:////tmp/funding-transfer.db")
sf = sessions(sqlite)
sync_sources(sf, Settings().source_file)
with sf.begin() as s:
    upsert(s, "manual", record, {"original": "SQLite evidence"})
    doc = ensure_document(s, "https://example.org/rules")
    associate(s, oid, doc, root=True)
    persist(s, doc, body, "application/octet-stream", Parsed(text=full_text))
target = migrate(url.set(database="fundingtransfer").render_as_string(hide_password=False))
transfer_database(sqlite, target)
with target.connect() as conn:
    row = conn.execute(select(Opportunity.__table__)).mappings().one()
    assert row["title"] == "Ääkköset ja ilmasto"
    assert row["total_budget"] == Decimal("1234567.89")
    blob = conn.execute(select(DocumentBlob.__table__)).mappings().one()
    assert gzip.decompress(blob["original_gzip"]) == body and blob["text"] == full_text
print("SQL Server integration passed: migrations, Unicode, decimals, large binary originals and full text, FSTP and priority filters, advance information, API filters, review concurrency, change feed, SQLite-to-SQL transfer.")
