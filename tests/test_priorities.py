import json
from datetime import date, datetime

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from funding.api import create_app
from funding.collector import upsert
from funding.document_parsers import parse_document
from funding.domain import Record, dump
from funding.funders import catalogue, dates_in_label, funding_pages, wordpress_calls
from funding.models import Source
from funding.priorities import load_priorities, priority_predicate
from funding.query import funding_view


def test_explicit_english_and_iso_deadlines_preserve_literal_timezone():
    label = "Call closes: 30 September 2026, 17.00 CEST"
    result = dates_in_label(label, "Europe/Brussels")[0]
    assert result.due_at == datetime(2026, 9, 30, 15)
    assert result.original == label
    literal_cet = dates_in_label("2026-09-27 23:00: CET", "Europe/Brussels")[0]
    assert literal_cet.due_at == datetime(2026, 9, 27, 22)
    assert dates_in_label("Deadline 18 June 2026", "Europe/Brussels")[0].due_at is None
    assert dates_in_label("Every September", "Europe/Brussels") == []


def test_wordpress_all_pages_and_application_deadline_not_confirmation_deadline():
    config = {"name": "EIT Urban Mobility", "api_url": "https://example.org/calls", "status_api": "https://example.org/status",
              "post_type": "call-for-proposals", "status_taxonomy": "status-call", "record_kind": "call"}
    row = {"id": 1, "type": "call-for-proposals", "status": "publish", "link": "https://example.org/grant",
           "title": {"rendered": "Innovation &amp; cities"}, "status-call": [500],
           "content": {"rendered": "<p>Deadline for applications: 8 July 2026 (17.00 CET)</p>"
                       "<p>Deadline for startups to confirm their participation: 14 September 2026</p>"}}
    class Client:
        def request(self, method, url, **kw):
            if url == config["status_api"]:
                return httpx.Response(200, json=[{"id": 500, "name": "Closed call"}])
            number = kw["params"]["page"]
            return httpx.Response(200, json=[{**row, "id": number, "link": f"https://example.org/grant-{number}"}],
                                  headers={"X-WP-Total": "2", "X-WP-TotalPages": "2"})
    records = [r for batch in wordpress_calls(Client(), config) for r, _ in batch.items]
    assert len(records) == 2 and {r.external_id for r in records} == {"1", "2"}
    assert records[0].title == "Innovation & cities" and records[0].source_status == "closed"
    assert records[0].deadlines[0].due_on == date(2026, 7, 8)
    assert records[0].deadlines[0].due_at == datetime(2026, 7, 8, 16)
    with pytest.raises(ValueError, match="pagination safety limit"):
        list(wordpress_calls(Client(), {**config, "max_pages": 1}))


def test_fstp_filter_uses_publisher_identity_not_free_text(database):
    cfg, engine, factory = database
    with factory.begin() as session:
        session.add(Source(id="eu-funding", name="EU", url="https://example.org", adapter="eu_funding", category="EU",
                           coverage="type 1 and 8", owner="test", enabled=True, config_json=dump({})))
        session.flush()
        for sid, ext, suffix in [("eu-funding", "cascade:42", "f1"), ("eu-funding", "HORIZON-01", "f2"), ("test", "cascade:43", "f3")]:
            upsert(session, sid, Record(external_id=ext, canonical_url=f"https://example.org/{suffix}", title="FSTP mentioned"), {})
        upsert(session, "test", Record(external_id="myr", canonical_url="https://example.org/myr", title="MYR",
                                       record_kind="advance_information", instrument="other"), {})
    with TestClient(create_app(cfg, engine)) as client:
        assert client.get("/v1/opportunities", params={"cascade": True}).json()["total"] == 1
        assert client.get("/v1/opportunities", params={"cascade": False}).json()["total"] == 3
        assert client.get("/v1/opportunities", params={"priority": 1}).json()["total"] == 1
        assert client.get("/v1/opportunities", params={"priority": 13}).status_code == 422
        info = client.get("/v1/opportunities", params={"record_kind": "advance_information"}).json()["items"][0]
        assert info["effective_status"] == "unknown" and info["deadline_on"] is None
        assert info["eligibility"] == "unreviewed"
        priorities = client.get("/v1/priorities").json()["items"]
        assert len(priorities) == 12 and priorities[0]["records"] == 1
        assert priorities[3]["missing_sources"] and not priorities[3]["complete_universe_claimed"]


def test_priority_predicate_rejects_unrecognised_configuration(database, tmp_path):
    _, engine, _ = database
    with pytest.raises(ValueError, match="Unsupported"):
        priority_predicate(funding_view(engine), {"rules": [{"sql": ["1=1"]}]})
    bad = tmp_path/"bad.json"
    bad.write_text(json.dumps([{"id": 1, "rules": [{}]}]))
    with pytest.raises(ValueError, match="entire registry"):
        load_priorities(bad)
    # Compilation exercises the same bound-parameter predicates on SQL Server.
    from sqlalchemy.dialects import mssql
    view = funding_view(engine)
    stmt = select(view.c.id).where(priority_predicate(view, load_priorities()[0]))
    compiled = stmt.compile(dialect=mssql.dialect())
    assert "cascade:" in compiled.params.values()


def test_funding_calendar_images_and_programme_manuals_are_retained(monkeypatch):
    html = b'<main><p>Full programme information and financing conditions for local public authorities and their international partners.</p><a href="/toolkit/programme-manual-2021-2027/">Manual</a><img src="/uploads/Call-calendar-slide.png" alt="Calendar"><img src="/logo.png" alt="Logo"></main>'
    parsed = parse_document(html, "text/html", "https://example.org/call-calendar")
    followed = {link.url for link in parsed.links if link.follow}
    assert "https://example.org/uploads/Call-calendar-slide.png" in followed
    assert "https://example.org/toolkit/programme-manual-2021-2027/" in followed
    assert "https://example.org/logo.png" not in followed
    monkeypatch.setattr("funding.ocr.read_png", lambda body: ("Calendar text", ["ocr_text_requires_human_verification"]))
    picture = parse_document(b"image", "image/png", "https://example.org/calendar.png")
    assert picture.text == "Calendar text" and picture.status == "partial_text"


def test_png_pixel_limit_is_checked_before_ocr():
    import struct

    from funding.ocr import read_png
    image = b"\x89PNG\r\n\x1a\n"+b"\x00"*8+struct.pack(">II", 100000, 100000)
    assert read_png(image)[1] == ["image_pixel_limit_original_retained"]


def test_broken_detail_retains_listing_and_other_calls():
    listing = '<main><p>Available funding instruments for municipal authorities and public institutions and their partners.</p><article><a href="/broken">Older grant</a></article><article><a href="/good">Current grant</a></article></main>'
    detail = '<main><h1>Current grant</h1><p>Public organisations can apply. The complete application conditions include a project plan, budget and partner responsibilities.</p></main>'
    def respond(request):
        if request.url.path == "/broken":
            return httpx.Response(404)
        return httpx.Response(200, text=listing if request.url.path == "/list" else detail)
    class Client:
        def request(self, method, url):
            with httpx.Client(transport=httpx.MockTransport(respond)) as client:
                response = client.request(method, url)
                response.raise_for_status()
                return response
    batch = list(catalogue(Client(), {"name": "Test", "url": "https://example.org/list",
        "card_selector": "article", "link_selector": "a", "fetch_details": True}))[0]
    assert len(batch.items) == 2 and batch.warnings and not batch.rejected
    broken, raw = batch.items[0]
    assert "detail_fetch_failed_listing_retained" in broken.quality_flags and raw["detail_error"]
    assert batch.items[1][0].detail_level == "full" and "project plan" in batch.items[1][0].description


def test_published_short_period_and_explicit_rolling_statement():
    dates = dates_in_label("18.2.-11.3.2026", "Europe/Helsinki")
    assert [d.due_on for d in dates] == [date(2026, 2, 18), date(2026, 3, 11)]
    # Do not invent the earlier year for an ambiguous cross-year short range.
    assert len(dates_in_label("18.12.-11.3.2026", "Europe/Helsinki")) == 1
    html = '<main><h1>Partnership financing</h1><p class="period">1.1.2024 - 31.12.2030</p><p class="rolling">Jatkuva haku: hankesuunnitelmat voi toimittaa ilman määräpäivää.</p><p>Hakijan tulee osallistua ekosysteemin yhteiseen tutkimus- ja kehittämistyöhön.</p></main>'
    class Client:
        def request(self, method, url):
            return httpx.Response(200, text=html, request=httpx.Request(method, url))
    record = list(funding_pages(Client(), {"name": "Test", "pages": [{"url": "https://example.org/grant",
        "record_kind": "call", "date_selector": ".period", "date_is_period": True,
        "rolling_selector": ".rolling"}]}))[0].items[0][0]
    assert record.source_status == "rolling" and record.deadline_model == "rolling" and record.deadlines == []
