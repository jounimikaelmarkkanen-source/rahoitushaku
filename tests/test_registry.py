from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from funding.api import create_app
from funding.collector import acquire, upsert
from funding.domain import Label, Record, due, enrich, now, opportunity_id
from funding.export import csv_text, transfer_database
from funding.models import Change, Deadline, Lease, Opportunity, SourceItem


def record(**kwargs):
    return Record(external_id="CALL-1", canonical_url="https://example.org/calls/1", title="Ilmaston ja tekoälyn haku", **kwargs)


def test_repeated_import_and_canonical_url_are_idempotent(database):
    _, _, factory = database
    with factory.begin() as s:
        assert upsert(s, "test", record(), {"id": "CALL-1"})
    with factory.begin() as s:
        assert not upsert(s, "test", record(), {"id": "CALL-1"})
        assert not upsert(s, "second", record(), {"id": "CALL-1"})
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(Opportunity)) == 1
        assert s.scalar(select(func.count()).select_from(SourceItem)) == 2
        assert s.scalar(select(func.count()).select_from(Change)) == 1
    assert opportunity_id("https://example.org/calls/1/?utm_source=test#page") == opportunity_id("https://example.org/calls/1")


def test_same_title_does_not_merge_different_calls(database):
    _, _, factory = database
    a, b = record(), record()
    b.canonical_url, b.external_id = "https://example.org/calls/2", "CALL-2"
    with factory.begin() as s:
        upsert(s, "test", a, {})
        upsert(s, "test", b, {})
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(Opportunity)) == 2


def test_source_update_preserves_review_and_marks_it_stale(database):
    cfg, engine, factory = database
    with factory.begin() as s:
        upsert(s, "test", record(), {})
    client = TestClient(create_app(cfg, engine))
    oid = opportunity_id(record().canonical_url)
    body = dict(expected_version=0, source_version=1, eligibility="conditional", evidence_url="https://example.org/rules", notes="Kumppanikonsortio tarvitaan")
    assert client.put(f"/v1/opportunities/{oid}/review", json=body).status_code == 200
    assert client.put(f"/v1/opportunities/{oid}/review", json=body).status_code == 409
    with factory.begin() as s:
        upsert(s, "test", record(description="Revised conditions"), {})
    data = client.get(f"/v1/opportunities/{oid}").json()
    assert data["needs_review"] == 1
    assert data["review_notes"] == "Kumppanikonsortio tarvitaan"
    assert data["version"] == 2
    body.update(expected_version=1, source_version=1)
    assert client.put(f"/v1/opportunities/{oid}/review", json=body).status_code == 409


def test_review_requires_source_evidence(database):
    cfg, engine, factory = database
    with factory.begin() as s:
        upsert(s, "test", record(), {})
    response = TestClient(create_app(cfg, engine)).put(f"/v1/opportunities/{opportunity_id(record().canonical_url)}/review", json=dict(expected_version=0, source_version=1, eligibility="eligible"))
    assert response.status_code == 422


def test_multistage_dates_and_no_fictional_time(database):
    _, _, factory = database
    dates = [due("2026-09-30", "Europe/Helsinki"), due("2027-02-15T17:00:00+01:00")]
    with factory.begin() as s:
        upsert(s, "test", record(deadlines=dates, deadline_model="two-stage"), {})
    with factory() as s:
        o = s.scalar(select(Opportunity))
        assert o.deadline_on == date(2027, 2, 15)
        assert o.deadline_at == datetime(2027, 2, 15, 16)
        assert s.scalars(select(Deadline).order_by(Deadline.stage)).first().due_at is None
        assert "stage_access_must_be_checked" in o.quality_flags_json


def test_filters_and_deadline_override_wrong_source_status(database):
    cfg, engine, factory = database
    with factory.begin() as s:
        upsert(s, "test", record(deadlines=[due("2020-09-09T12:00:00Z")], source_status="open", tags=[Label(kind="region", value="Pirkanmaa")]), {})
    client = TestClient(create_app(cfg, engine))
    assert client.get("/v1/opportunities?status=closed&theme=Ilmasto%20ja%20energia&region=Pirkanmaa").json()["total"] == 1
    assert client.get("/v1/opportunities?status=open").json()["total"] == 0
    assert client.get("/v1/opportunities?q=%25").json()["total"] == 0  # literal %, not SQL wildcard
    assert client.get("/v1/opportunities?limit=1001").status_code == 422
    assert client.get("/v1/opportunities?changed_since=2026-01-01T12:00:00").status_code == 422


def test_changes_watermark_freezes_pagination(database):
    cfg, engine, factory = database
    with factory.begin() as s:
        upsert(s, "test", record(), {})
    client = TestClient(create_app(cfg, engine))
    first = client.get("/v1/changes?limit=1").json()
    with factory.begin() as s:
        upsert(s, "test", record(description="updated"), {})
    second = client.get(f"/v1/changes?after_id={first['next_after_id']}&through_id={first['through_id']}").json()
    assert second["items"] == []
    latest = client.get(f"/v1/changes?after_id={first['next_after_id']}").json()
    assert len(latest["items"]) == 1


def test_lease_prevents_overlapping_collectors(database):
    _, _, factory = database
    assert acquire(factory, "collector", "first")
    assert not acquire(factory, "collector", "second")
    with factory.begin() as s:
        s.get(Lease, "collector").expires_at = now()-timedelta(minutes=1)
    assert acquire(factory, "collector", "second")


def test_excel_csv_injection_is_escaped():
    result = csv_text([{"title": '=HYPERLINK("https://evil.test")'}], ["title"])
    assert "'=HYPERLINK" in result


def test_date_only_expiry_respects_helsinki_summer_and_winter_time():
    summer = enrich(record(deadlines=[due("2026-06-30", "Europe/Helsinki")]))
    winter = enrich(record(deadlines=[due("2026-12-31", "Europe/Helsinki")]))
    assert summer.deadline_at is None
    assert summer.deadline_expires_at == datetime(2026, 6, 30, 21)
    assert winter.deadline_expires_at == datetime(2026, 12, 31, 22)


def test_finnish_case_insensitive_search_and_funder_filter(database):
    cfg, engine, factory = database
    r = record(funder="Säätiö A")
    r.title = "Ääkköset"
    with factory.begin() as s:
        upsert(s, "test", r, {})
    client = TestClient(create_app(cfg, engine))
    assert client.get("/v1/opportunities", params={"q": "ÄÄKKÖSET", "funder": "Säätiö A"}).json()["total"] == 1
    assert client.get("/v1/opportunities", params={"funder": "Säätiö B"}).json()["total"] == 0


def test_unreviewed_note_does_not_remove_item_from_review_queue(database):
    cfg, engine, factory = database
    with factory.begin() as s:
        upsert(s, "test", record(), {})
    client = TestClient(create_app(cfg, engine))
    oid = opportunity_id(record().canonical_url)
    response = client.put(f"/v1/opportunities/{oid}/review", json={"expected_version": 0, "source_version": 1, "eligibility": "unreviewed", "notes": "Selvitys kesken"})
    assert response.status_code == 200
    assert client.get(f"/v1/opportunities/{oid}").json()["needs_review"] == 1


def test_api_entra_mode_fails_closed(database):
    cfg, engine, _ = database
    cfg.auth_mode = "entra"
    cfg.entra_tenant_id = "12345678-1234-1234-1234-123456789012"
    cfg.entra_audience = "api://funding"
    client = TestClient(create_app(cfg, engine))
    assert client.get("/v1/opportunities").status_code == 401
    assert client.get("/health/live").status_code == 200


def test_database_transfer_refuses_existing_target(database):
    _, engine, _ = database
    with pytest.raises(ValueError, match="not empty"):
        transfer_database(engine, engine)
