from datetime import date, datetime

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from funding.api import create_app
from funding.collector import upsert
from funding.domain import Record, enrich
from funding.funders import catalogue, dates_in_label, html_record, semantic_text, sitra, sitra_record


def sitra_row(identifier=123):
    return {"id": identifier, "type": "funding_request", "status": "publish",
            "link": f"https://www.sitra.fi/rahoitushaku/example-{identifier}/",
            "title": {"rendered": "Julkisen sektorin rahoitushaku"},
            "content": {"rendered": '''<h1>Julkisen sektorin rahoitushaku</h1>
<div class="single-meta--program"><p class="single-meta__data">Tuottavuus</p></div>
<div class="single-meta--start-datetime"><p class="single-meta__data">22.6.2026 12:00</p></div>
<div class="single-meta--end-datetime"><p class="single-meta__data">15.9.2026 12:00</p></div>
<div class="single-meta--status"><p class="single-meta__data">Avoinna</p></div>
<template><details><summary>Kuka voi hakea?</summary>
<p>Rahoitusta voivat hakea vain ehdot täyttävät kunnat. Lue kaikki ehdot.</p>
</details></template><p>Kysymykset 14.8.2026, toteutus päättyy 30.11.2026.</p>'''}}


def test_sitra_metadata_deadline_and_accordion_evidence():
    record, raw = sitra_record(sitra_row())
    record = enrich(record)
    assert record.funder == "Sitra" and record.record_kind == "call"
    assert record.source_status == "open"
    assert record.deadline_at == datetime(2026, 9, 15, 9, 0)
    assert record.deadline_on == date(2026, 9, 15)
    assert "vain ehdot täyttävät kunnat" in raw["text"]
    assert "vain ehdot täyttävät kunnat" in record.eligibility_text
    assert "<template>" not in semantic_text(sitra_row()["content"]["rendered"])


def test_undated_annual_scheme_does_not_invent_year_or_open_round():
    config = {"name": "Säätiö", "record_kind": "funding_scheme"}
    record = html_record("Apuraha", "https://example.org/grant", "Yleinen haku 1.–15.9. Vanhat päätökset 15.9.2025.", config,
                         date_label="15.9.2025")
    assert record.source_status == "unknown" and record.deadlines == []
    assert record.record_kind == "funding_scheme"
    assert dates_in_label("1.–15.9.", "Europe/Helsinki") == []


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.visited = []

    def request(self, method, url, **kwargs):
        key = str(kwargs.get("params", {}).get("page")) if kwargs.get("params") else url
        self.visited.append(key)
        data = self.responses[key]
        return httpx.Response(200, request=httpx.Request(method, url), **data)


def card(title, target="grant", date_label="Deadline 24.09.2026"):
    return f'<article><h4><a href="/{target}">{title}</a></h4><span class="due">{date_label}</span><p>Published information about funding for projects and international collaboration.</p></article>'


def page(cards, next_page=False):
    return {"text": f'<main>{cards}</main>'+('<a rel="next" href="?page=1">Next</a>' if next_page else '')}


CONFIG = {"name": "Nordic", "url": "https://example.org/calls", "card_selector": "article",
          "link_selector": "h4 a", "date_selector": ".due", "next_selector": 'a[rel="next"]',
          "exclude_title": "invitation to tender|akkreditointihaku", "language": "en"}


def test_catalogue_pagination_deduplicates_identical_cards_excludes_nonfunding():
    common = card("Grant")
    client = FakeClient({CONFIG["url"]: page(common+card("Invitation to tender", "tender"), True),
                         CONFIG["url"]+"?page=1": page(common+card("Another grant", "grant2"))})
    records = [record for batch in catalogue(client, CONFIG) for record, _ in batch.items]
    assert len(records) == 2 and len({r.canonical_url for r in records}) == 2
    assert records[0].deadlines[0].due_on == date(2026, 9, 24)
    assert records[0].source_status == "unknown"  # future deadline alone is not an opening status
    assert len(client.visited) == 2


def test_catalogue_repeated_conflicting_card_and_parser_drift_fail():
    client = FakeClient({CONFIG["url"]: page(card("Grant"), True),
                         CONFIG["url"]+"?page=1": page(card("Changed grant"))})
    with pytest.raises(ValueError, match="Conflicting"):
        list(catalogue(client, CONFIG))
    client = FakeClient({CONFIG["url"]: {"text": '<main><p>'+('Loading ' * 40)+'</p></main>'}})
    with pytest.raises(ValueError, match="cards missing"):
        list(catalogue(client, CONFIG))


def test_sitra_paginated_totals_checked():
    headers = {"X-WP-Total": "2", "X-WP-TotalPages": "2"}
    client = FakeClient({"1": {"json": [sitra_row(1)], "headers": headers},
                         "2": {"json": [sitra_row(2)], "headers": headers}})
    assert len([r for b in sitra(client, {"api_url": "https://www.sitra.fi/wp-json/wp/v2/funding_request"}) for r in b.items]) == 2
    headers["X-WP-Total"] = "3"
    with pytest.raises(ValueError, match="pagination mismatch"):
        list(sitra(client, {"api_url": "https://www.sitra.fi/wp-json/wp/v2/funding_request"}))


def test_funder_filter_and_scheme_directory_do_not_approve_eligibility(database):
    cfg, engine, factory = database
    with factory.begin() as session:
        for kind in ["call", "funding_scheme"]:
            record = Record(external_id=kind, canonical_url=f"https://example.org/{kind}",
                            title="Rahoitus", funder="SITRA" if kind == "call" else "Sitra", record_kind=kind)
            assert upsert(session, "test", record, {"text": "original"})
            assert not upsert(session, "test", Record.model_validate(record.model_dump()), {"text": "original"})
    with TestClient(create_app(cfg, engine)) as client:
        result = client.get("/v1/opportunities", params={"funder": "Sitra", "record_kind": "funding_scheme"}).json()
        assert result["total"] == 1
        assert result["items"][0]["eligibility"] == "unreviewed"
        funder = client.get("/v1/funders").json()["items"][0]
        assert funder == {"funder": "SITRA", "records": 2, "calls": 1, "schemes": 1, "advance_information": 0, "open_or_forthcoming": 0, "unknown_status": 2}


def test_upgrade_v1_to_v2_preserves_records(tmp_path, monkeypatch):
    from funding.domain import dump, now
    from funding.schema_v1 import metadata
    url = f"sqlite:///{tmp_path}/migration.db"
    monkeypatch.setenv("FUNDING_DATABASE_URL", url)
    command.upgrade(Config("alembic.ini"), "0001")
    engine = create_engine(url)
    record = Record(external_id="old", canonical_url="https://example.org/old", title="Vanha haku")
    values = record.model_dump(exclude={"tags", "deadlines", "quality_flags", "record_kind"})
    values.update(id="old", source_id="old-source", content_hash="x"*64, quality_flags_json="[]", version=1,
                  first_seen_at=now(), last_seen_at=now(), updated_at=now())
    with engine.begin() as conn:
        conn.execute(metadata.tables["sources"].insert(), {"id": "old-source", "name": "Old", "url": "https://example.org", "adapter": "manual",
                     "category": "test", "coverage": "test", "owner": "test", "enabled": False, "config_json": dump({})})
        conn.execute(metadata.tables["opportunities"].insert(), values)
    command.upgrade(Config("alembic.ini"), "head")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT title,record_kind,version FROM v_funding")).one() == ("Vanha haku", "call", 1)
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "0007"
    engine.dispose()


def test_new_default_kind_does_not_invalidate_existing_reviews(database):
    from funding.domain import digest, dump, opportunity_id
    from funding.models import Opportunity
    _, _, factory = database
    record = enrich(Record(external_id="old", canonical_url="https://example.org/old", title="Haku"))
    with factory.begin() as session:
        upsert(session, "test", record, {"data": "unchanged"})
        opportunity = session.get(Opportunity, opportunity_id(record.canonical_url))
        opportunity.content_hash = digest(dump(record.model_dump(mode="json", exclude={"record_kind"})))
        assert not upsert(session, "test", record, {"data": "unchanged"})
        assert opportunity.version == 1
