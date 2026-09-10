import gzip
import io
import json

import httpx
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import select

from funding.api import create_app
from funding.collector import upsert
from funding.document_parsers import Link, Parsed, parse_document, referenced_codes
from funding.documents import (
    associate,
    enrich_documents,
    ensure_document,
    eu_has_content,
    fetch_document,
    persist,
    reextract_documents,
    refresh_graph,
)
from funding.domain import Record, digest, opportunity_id
from funding.http import PublicClient
from funding.models import Change, Document, DocumentBlob, DocumentVersion, Opportunity, OpportunityDocument


def test_hae_full_sections_languages_and_conditional_standard_terms():
    body = json.dumps({"hasVakioehdot": True, "ehto": {"fi": "Kunta voi hakea.", "sv": "En kommun kan ansöka."},
                       "lisa": '<a href="https://example.org/terms.pdf">Liite ja ehdot</a>', "osuus": 80}).encode()
    parsed = parse_document(body, "application/json", "https://www.haeavustuksia.fi/api/haku/va-1/hakuilmoitus/yleistiedot", "hae_json")
    assert "Kunta voi hakea" in parsed.text and "kommun" in parsed.text and "80" in parsed.text
    assert len([link for link in parsed.links if link.role == "required_section"]) == 5
    assert any(link.url.endswith("terms.pdf") and link.follow for link in parsed.links)


def test_macro_budget_workbooks_are_followed_and_keep_their_file_type():
    import zipfile

    from funding.document_parsers import infer_media_type
    from funding.export import original_extension
    source = b'<main>'+b'Full funding conditions. '*10+b'<a href="/budget.xlsm">Budget</a></main>'
    assert parse_document(source, "text/html", "https://example.org/call").links[0].follow
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", '<Types><Override ContentType="application/vnd.ms-excel.sheet.macroEnabled.main+xml"/></Types>')
        archive.writestr("xl/workbook.xml", "<workbook><sheet>Budget instructions</sheet></workbook>")
    media = infer_media_type(buffer.getvalue(), "application/octet-stream")
    assert original_extension(media) == ".xlsm"
    parsed = parse_document(buffer.getvalue(), media, "https://example.org/budget.xlsm")
    assert "Budget instructions" in parsed.text and parsed.status == "partial_text"


def test_link_policy_reaches_terms_in_accordion_and_retains_unfollowed_references():
    html = b'<html><title>Call</title><main><p>'+b'Long full call text. '*15+b'</p><template><a href="/rules">Conditions and guidelines</a></template><a href="/about">About us</a><a href="/privacy">Privacy terms</a></main></html>'
    result = parse_document(html, "text/html", "https://example.org/call")
    links = {link.url: link.follow for link in result.links}
    assert links["https://example.org/rules"] is True
    assert links["https://example.org/about"] is False
    assert links["https://example.org/privacy"] is False
    assert result.status == "extracted"


def test_qa_article_and_opaque_conditions_links_use_local_context():
    html = '''<main><p>Hakua koskevat kysymykset ja vastaukset julkaistaan
      <a href="/artikkelit/kysymyksia-ja-vastauksia-rahoitushausta/">tässä artikkelissa</a>.</p>
      <p>Complete funding conditions are available <strong><a href="/item/73">here</a></strong>.</p>
      <p>Kysymykset ja vastaukset: <a href="/privacy">tietosuoja</a>.</p>
      <p>Our organisation: <a href="/about">here</a>.</p>
      <a href="/questions-and-answers-call-2026">English</a>
      <a href="/fragor-och-svar-utlysning">Svenska</a></main>'''.encode()
    result = parse_document(html, "text/html", "https://example.org/call")
    links = {link.url: link for link in result.links}
    assert links["https://example.org/artikkelit/kysymyksia-ja-vastauksia-rahoitushausta/"].follow
    assert links["https://example.org/item/73"].follow
    assert "funding conditions" in links["https://example.org/item/73"].title
    assert links["https://example.org/questions-and-answers-call-2026"].follow
    assert links["https://example.org/fragor-och-svar-utlysning"].follow
    assert not links["https://example.org/privacy"].follow
    assert not links["https://example.org/about"].follow


def test_source_shell_is_not_claimed_as_full_content_and_scanned_pdf_is_visible():
    shell = parse_document(b'<html><body><app-root></app-root></body></html>', 'text/html', 'https://example.org')
    assert shell.status == "unreadable"
    pdf = PdfWriter()
    pdf.add_blank_page(595, 842)
    output = io.BytesIO()
    pdf.write(output)
    parsed = parse_document(output.getvalue(), "application/pdf", "https://example.org/scan.pdf")
    assert parsed.page_count == 1 and parsed.status == "partial_text"
    assert any("ocr" in flag for flag in parsed.flags)


def test_identical_pdf_ocr_is_reused_and_relative_attachment_links_are_rebased(monkeypatch):
    from pypdf.annotations import Link as PdfLink
    calls = []
    def ocr(body, pages):
        calls.append(pages)
        return {1: "Recognised source text."}, ["ocr_text_requires_human_verification"]
    monkeypatch.setattr("funding.ocr.read_scan_pages", ocr)
    pdf = PdfWriter()
    pdf.add_metadata({"/Title": "PDF cache and relative-link test"})
    pdf.add_blank_page(595, 842)
    pdf.add_annotation(0, PdfLink(rect=(0, 0, 100, 100), url="appendix.pdf"))
    pdf.add_annotation(0, PdfLink(rect=(0, 0, 100, 100), url="https://example.org/a/appendix.pdf"))
    output = io.BytesIO()
    pdf.write(output)
    first = parse_document(output.getvalue(), "application/pdf", "https://example.org/a/rules.pdf")
    first.flags.append("caller-specific flag")
    second = parse_document(output.getvalue(), "application/pdf", "https://example.org/b/rules.pdf")
    assert len(calls) == 1 and "Recognised source text." in second.text
    assert "caller-specific flag" not in second.flags
    assert first.links[0].url == "https://example.org/a/appendix.pdf"
    assert second.links[0].url == "https://example.org/b/appendix.pdf"
    assert len(first.links) == 1 and len(second.links) == 2


def add_opportunity(factory):
    record = Record(external_id="call", canonical_url="https://example.org/call", title="Kaupungin haku")
    with factory.begin() as session:
        upsert(session, "test", record, {})
    return opportunity_id(record.canonical_url)


def test_transport_alias_does_not_invalidate_unrelated_reviews_for_identical_content(database):
    _, _, factory = database
    first = add_opportunity(factory)
    second_record = Record(external_id="other", canonical_url="https://example.org/other", title="Toinen haku")
    body = b"Identical full funding conditions."
    flag = "source_http_link_retrieved_over_https"
    with factory.begin() as session:
        upsert(session, "test", second_record, {})
        a = ensure_document(session, "https://example.org/terms")
        associate(session, first, a, root=True)
        persist(session, a, body, "text/plain", Parsed(text=body.decode()))
        before = session.get(Opportunity, first).version
        b = ensure_document(session, "http://example.org/terms")
        associate(session, opportunity_id(second_record.canonical_url), b, root=True)
        parsed = Parsed(text=body.decode(), flags=[flag])
        persist(session, b, body, "text/plain", parsed, final_url=a.url)
        assert session.get(Opportunity, first).version == before
        assert parsed.flags == [flag]  # The caller's evidence is not mutated.
        blob = session.get(DocumentBlob, a.current_sha256)
        assert flag not in json.loads(blob.flags_json)
        # Normalise an older archive's transport label without a false content event.
        blob.flags_json = json.dumps([flag])
        session.flush()
        assert persist(session, a, body, "text/plain", Parsed(text=body.decode())) is False
        assert session.get(Opportunity, first).version == before
        assert json.loads(blob.flags_json) == []


def test_shared_document_updates_every_related_call_once_and_keeps_loaded_versions_current(database):
    _, _, factory = database
    unrelated = add_opportunity(factory)
    with factory.begin() as session:
        doc = ensure_document(session, "https://example.org/shared-terms")
        ids = []
        for i in range(105):
            record = Record(external_id=f"shared-{i}", canonical_url=f"https://example.org/shared/{i}", title=f"Call {i}")
            upsert(session, "test", record, {})
            oid = opportunity_id(record.canonical_url)
            ids.append(oid)
            associate(session, oid, doc, root=True)
        loaded = session.get(Opportunity, ids[0])
        body = b"Complete common funding conditions."
        persist(session, doc, body, "text/plain", Parsed(text=body.decode()))
        assert loaded.version == 2
        assert set(session.scalars(select(Opportunity.version).where(Opportunity.id.in_(ids)))) == {2}
        assert session.get(Opportunity, unrelated).version == 1
        assert len(list(session.scalars(select(Change.id).where(Change.kind == "document_added")))) == 105
        persist(session, doc, body, "text/plain", Parsed(text=body.decode()))
        assert loaded.version == 2
        assert len(list(session.scalars(select(Change.id).where(Change.kind == "document_added")))) == 105


def test_deep_graph_cycles_shared_blobs_versioning_and_removed_links(database):
    _, _, factory = database
    oid = add_opportunity(factory)
    with factory.begin() as session:
        root = ensure_document(session, "https://example.org/call")
        associate(session, oid, root, root=True)
        persist(session, root, b"root", "text/plain", Parsed(text="Call", links=[Link("https://example.org/terms", follow=True)]))
    refresh_graph(factory, [oid])
    with factory.begin() as session:
        terms = session.get(Document, digest("https://example.org/terms"))
        persist(session, terms, b"terms", "text/plain", Parsed(text="Own contribution 20%", links=[
            Link("https://example.org/call", follow=True), Link("https://example.org/annex.pdf", follow=True)]))
    refresh_graph(factory, [oid], max_depth=1)
    with factory() as session:
        annex = session.get(OpportunityDocument, (oid, digest("https://example.org/annex.pdf")))
        assert annex.limitation == "depth_limit"
        assert len(session.scalars(select(OpportunityDocument)).all()) == 3
    with factory.begin() as session:
        root = session.get(Document, digest("https://example.org/call"))
        original_version = session.get(Opportunity, oid).version
        persist(session, root, b"updated", "text/plain", Parsed(text="Updated call, attachment removed"))
        assert session.get(Opportunity, oid).version == original_version+1
        persist(session, root, b"updated", "text/plain", Parsed(text="Updated call, attachment removed"))
        assert session.get(Opportunity, oid).version == original_version+1
    refresh_graph(factory, [oid])
    with factory() as session:
        assert session.get(OpportunityDocument, (oid, digest("https://example.org/terms"))).active is False
        assert len(session.scalars(select(DocumentVersion).where(DocumentVersion.document_id == root.id)).all()) == 2
        for blob in session.scalars(select(DocumentBlob)):
            assert digest(gzip.decompress(blob.original_gzip).decode()) == blob.sha256


def test_api_full_text_filter_original_integrity_and_old_version_download(database):
    cfg, engine, factory = database
    oid = add_opportunity(factory)
    with factory.begin() as session:
        doc = ensure_document(session, "https://example.org/rules.html")
        associate(session, oid, doc, root=True)
        persist(session, doc, b"<script>untrusted</script>", "text/html", Parsed(text="Rahoituksen omarahoitus 20 prosenttia."))
    client = TestClient(create_app(cfg, engine))
    rows = client.get("/v1/opportunities", params={"content_q": "omarahoitus", "content_state": "collected_unverified"}).json()
    assert rows["total"] == 1
    inventory = client.get(f"/v1/opportunities/{oid}/documents").json()
    assert inventory["completeness_verified"] is False
    item = inventory["items"][0]
    original = client.get(item["original_url"])
    assert original.content == b"<script>untrusted</script>"
    assert original.headers["content-type"] == "application/octet-stream"
    assert original.headers["content-disposition"].startswith("attachment;")
    assert client.get(item["text_url"]).json()["full_text"].endswith("20 prosenttia.")
    assert client.get(item["original_url"], params={"sha256": "f"*64}).status_code == 404


def test_http_failure_and_bad_parser_retain_honest_state(database):
    cfg, _, _ = database
    def transport(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.path == "/missing":
            return httpx.Response(404)
        return httpx.Response(200, content=b"not JSON", headers={"content-type": "application/json"})
    def factory(cfg, _):
        return PublicClient(cfg, ["example.org"], transport=httpx.MockTransport(transport))
    base = {"etag": None, "last_modified": None, "parser": "hae_json"}
    result = fetch_document(cfg, {**base, "url": "https://example.org/missing"}, factory)
    assert result["http_status"] == 404 and "error" in result
    result = fetch_document(cfg, {**base, "url": "https://example.org/error"}, factory)
    assert result["body"] == b"not JSON" and result["parsed"].status == "unreadable"


def test_conditional_get_304_is_not_followed_as_a_redirect(database):
    cfg, _, _ = database
    def transport(request):
        return httpx.Response(404 if request.url.path == "/robots.txt" else 304)
    client = PublicClient(cfg, ["example.org"], transport=httpx.MockTransport(transport))
    assert client.request("GET", "https://example.org/call").status_code == 304
    client.close()


def test_transient_server_disconnect_is_retried(database, monkeypatch):
    cfg, _, _ = database
    attempts = 0
    monkeypatch.setattr("funding.http.time.sleep", lambda _: None)
    def transport(request):
        nonlocal attempts
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        attempts += 1
        if attempts == 1:
            raise httpx.RemoteProtocolError("Server disconnected", request=request)
        return httpx.Response(200, content=b"Full notice")
    client = PublicClient(cfg, ["example.org"], transport=httpx.MockTransport(transport))
    assert client.request("GET", "https://example.org/call").content == b"Full notice"
    assert attempts == 2
    client.close()


def test_rate_limit_honours_retry_after_across_clients_and_redirect_origins(database, monkeypatch):
    from datetime import timedelta
    from email.utils import format_datetime

    from funding.domain import now
    from funding.http import RateLimited
    cfg, _, _ = database
    monkeypatch.setattr(PublicClient, "cooldowns", {})
    requests = []
    until = now()+timedelta(hours=2)
    def transport(request):
        requests.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.host == "example.org":
            return httpx.Response(302, headers={"location": "https://limited.example.org/file.pdf"})
        return httpx.Response(429, headers={"Retry-After": format_datetime(until)})
    def client_factory(config, _):
        return PublicClient(config, ["example.org", "limited.example.org"], transport=httpx.MockTransport(transport))
    row = {"url": "https://example.org/file.pdf", "parser": "web", "etag": None, "last_modified": None}
    first = fetch_document(cfg, row, client_factory)
    assert first["attempted"] and abs((first["deferred_until"]-until).total_seconds()) < 1
    assert "https://limited.example.org" in first["error"]
    count = len(requests)
    second = fetch_document(cfg, {**row, "url": "https://limited.example.org/other.pdf"}, client_factory)
    assert not second["attempted"] and len(requests) == count
    assert second["deferred_until"] == first["deferred_until"]
    assert isinstance(RateLimited("https://example.org", until), RuntimeError)


def test_slow_robots_origin_does_not_block_other_funders(database, monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from funding.documents import DocumentClient
    cfg, _, _ = database
    started, release = threading.Event(), threading.Event()
    def robots(self, url):
        if "slow.example.org" in url:
            started.set()
            assert release.wait(3)
        return True
    monkeypatch.setattr(PublicClient, "_robots_allowed", robots)
    clients = [DocumentClient(cfg, [], transport=httpx.MockTransport(lambda _: httpx.Response(200))) for _ in range(2)]
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            slow = pool.submit(clients[0]._robots_allowed, "https://slow.example.org/call")
            try:
                assert started.wait(1)
                fast = pool.submit(clients[1]._robots_allowed, "https://fast.example.org/call")
                fast.result(timeout=1)
            finally:
                release.set()
            slow.result(timeout=1)
    finally:
        for client in clients:
            client.close()


def test_rate_limited_document_resumes_without_false_network_observations(database, monkeypatch):
    from datetime import timedelta

    from funding.domain import now
    cfg, _, factory = database
    monkeypatch.setattr(PublicClient, "cooldowns", {})
    oid = add_opportunity(factory)
    until = now()+timedelta(hours=1)
    with factory.begin() as session:
        root = ensure_document(session, "https://example.org/call")
        associate(session, oid, root, root=True)
        root.error = f"RATE_LIMIT|https://example.org|{until.isoformat()}"
        root.next_check_at = until
        other = ensure_document(session, "https://example.org/terms.pdf")
        associate(session, oid, other, root=True)
        did = other.id
    requests = []
    def client_factory(config, _):
        return PublicClient(config, ["example.org"], transport=httpx.MockTransport(lambda r: requests.append(r) or httpx.Response(200)))
    enrich_documents(factory, cfg, pending_only=True, client_factory=client_factory)
    with factory() as session:
        doc = session.get(Document, did)
        assert doc.state == "pending" and doc.next_check_at == until
        assert doc.attempts == 0 and doc.checked_at is None and doc.http_status is None
    assert requests == []


def test_attachment_landing_page_is_not_complete_and_does_not_contaminate_valid_page(database):
    from funding.documents import mark_missing_attachment
    cfg, _, factory = database
    oid = add_opportunity(factory)
    body = b'<main>'+b'Publication catalogue content. '*15+b'<a href="/irrelevant.pdf">Guide</a></main>'
    with factory.begin() as session:
        attachment = ensure_document(session, "https://example.org/lost.pdf")
        associate(session, oid, attachment, root=True)
        parsed = parse_document(body, "text/html", "https://example.org/publications")
        mark_missing_attachment(attachment.url, "text/html", parsed)
        persist(session, attachment, body, "text/html", parsed)
        assert attachment.extraction_status == "unreadable" and attachment.error == "DOCUMENT_DOWNLOAD_RETURNED_HTML"
        assert not any(link.follow for link in parsed.links)
        page = ensure_document(session, "https://example.org/publications")
        persist(session, page, body, "text/html", parse_document(body, "text/html", page.url))
        assert page.extraction_status == "extracted" and page.error is None
        assert attachment.extraction_status == "unreadable"


def test_helpdesk_redirect_to_front_page_is_not_the_requested_detail(database):
    from funding.documents import document_response_issue, mark_missing_attachment
    _, _, factory = database
    body = b'<main>'+b'Generic funding organisation home page. '*10+b'<a href="/other.pdf">Guide</a></main>'
    with factory.begin() as session:
        doc = ensure_document(session, "https://example.org/helpdesk/call-123")
        parsed = parse_document(body, "text/html", "https://example.org")
        mark_missing_attachment(doc.url, "text/html", parsed, "https://example.org")
        persist(session, doc, body, "text/html", parsed, final_url="https://example.org")
        assert doc.error == "DETAIL_REDIRECTED_TO_FRONT_PAGE" and doc.extraction_status == "unreadable"
        assert not any(link.follow for link in parsed.links)
    assert document_response_issue("https://example.org/fi/", "text/html", "https://example.org") is None
    assert document_response_issue("https://example.org/helpdesk/call", "text/html", "https://example.org/helpdesk/call/") is None


def test_eura_text_includes_selected_criteria_only():
    assert referenced_codes({"criteria": ["VP_2"]}, {"criteria": {"VP_1": "Unselected", "VP_2": "Required"}}) == {
        "criteria": {"VP_2": "Required"}}


def test_eu_detail_detection_requires_populated_content_and_recognizes_cascade_field():
    assert not eu_has_content({"documents": [{"metadata": {"description": [], "topicConditions": ["<p>&nbsp;</p>"]}}]})
    assert eu_has_content({"documents": [{"metadata": {"description": [], "beneficiaryAdministration": ["<p>Complete cascade call conditions.</p>"]}}]})


def test_malformed_source_link_does_not_discard_the_full_notice():
    parsed = parse_document(b'{"terms":"Full terms https://[10:05]/rules.pdf; more conditions"}',
                            "application/json", "https://example.org/call")
    assert "more conditions" in parsed.text and parsed.status == "partial_text"
    assert any(flag.startswith("malformed_source_url:") for flag in parsed.flags)


def test_only_published_form_preview_is_followed_without_application_endpoints():
    base = "https://www.haeavustuksia.fi/api/haku/va-1/hakuilmoitus/yleistiedot"
    parsed = parse_document(b'{"isHakulomakePreviewEligible":true}', "application/json", base, "hae_json")
    assert len(parsed.links) == 4
    assert all("/hakemuslomake/" in link.url and link.follow for link in parsed.links)
    assert not parse_document(b'{"isHakulomakePreviewEligible":false}', "application/json", base, "hae_json").links


def test_document_cap_is_visible_without_creating_unbounded_associations(database):
    _, _, factory = database
    oid = add_opportunity(factory)
    with factory.begin() as session:
        root = ensure_document(session, "https://example.org/call")
        associate(session, oid, root, root=True)
        persist(session, root, b"call", "text/plain", Parsed(text="Call", links=[
            Link(f"https://example.org/terms-{i}", follow=True) for i in range(400)]))
    refresh_graph(factory, [oid], max_documents=10)
    with factory() as session:
        mappings = session.scalars(select(OpportunityDocument)).all()
        assert len(mappings) == 11
        assert sum(m.limitation == "document_limit" for m in mappings) == 1
        assert len(session.scalars(select(Document)).all()) == 11


def test_resumable_pipeline_discovers_deeper_links_and_refreshes_304(database):
    cfg, _, factory = database
    oid = add_opportunity(factory)
    requests = []
    def transport(request):
        requests.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.headers.get("if-none-match"):
            return httpx.Response(304)
        content = b"<main>"+b"Complete funding conditions. "*20
        content += b'<a href="/terms">Terms and conditions</a></main>' if request.url.path == "/call" else b"</main>"
        return httpx.Response(200, content=content, headers={"content-type": "text/html", "etag": '"v1"'})
    def client_factory(cfg, _):
        return PublicClient(cfg, ["example.org"], transport=httpx.MockTransport(transport))
    result = enrich_documents(factory, cfg, workers=2, max_fetches=1, client_factory=client_factory)
    assert result["current_documents"] == {"fetched": 1, "pending": 1}
    result = enrich_documents(factory, cfg, workers=2, client_factory=client_factory)
    assert result["calls"] == {"collected_unverified": 1}
    assert requests.count("/call") == 1 and requests.count("/terms") == 1
    with factory.begin() as session:
        for doc in session.scalars(select(Document)):
            doc.next_check_at = None
        version = session.get(Opportunity, oid).version
    enrich_documents(factory, cfg, workers=2, client_factory=client_factory)
    with factory() as session:
        assert session.get(Opportunity, oid).version == version
        assert all(d.http_status == 304 and d.attempts == 2 for d in session.scalars(select(Document)))


def test_current_only_finishes_deep_links_without_fetching_or_retrying_history(database):
    from datetime import timedelta

    from funding.domain import now
    cfg, _, factory = database
    stamp = now()
    records = [
        Record(external_id="open", canonical_url="https://example.org/open", title="Open", source_status="open"),
        Record(external_id="scheme", canonical_url="https://example.org/scheme", title="Scheme", record_kind="funding_scheme"),
        Record(external_id="expired", canonical_url="https://example.org/expired", title="Expired", source_status="open",
               deadline_at=stamp-timedelta(minutes=1)),
        Record(external_id="cancelled", canonical_url="https://example.org/cancelled", title="Cancelled", source_status="cancelled"),
    ]
    with factory.begin() as session:
        for record in records:
            upsert(session, "test", record, {})
        old = ensure_document(session, records[2].canonical_url)
        associate(session, opportunity_id(records[2].canonical_url), old, root=True)
        old.state, old.next_check_at = "failed", stamp+timedelta(days=1)
        old_id = old.id
    requested = []
    def transport(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        requested.append(request.url.path)
        body = b"<main>"+b"Complete published funding conditions. "*10
        if request.url.path == "/open":
            body += b'<a href="/terms">General conditions</a>'
        elif request.url.path == "/terms":
            body += b'<a href="/faq">Questions and answers</a>'
        return httpx.Response(200, content=body+b"</main>", headers={"content-type": "text/html"})
    def client_factory(config, _):
        return PublicClient(config, ["example.org"], transport=httpx.MockTransport(transport))
    enrich_documents(factory, cfg, current_only=True, pending_only=True, retry_failed=True, client_factory=client_factory)
    assert set(requested) == {"/open", "/scheme", "/terms", "/faq"}
    with factory() as session:
        old = session.get(Document, old_id)
        assert old.next_check_at == stamp+timedelta(days=1) and old.state == "failed"
        assert all(doc.state == "fetched" for doc in session.scalars(select(Document).where(Document.id != old_id)))


def test_offline_reextraction_preserves_original_and_observation_dates(database):
    from datetime import datetime
    _, _, factory = database
    oid = add_opportunity(factory)
    old = datetime(2024, 1, 2, 3, 4, 5)
    with factory.begin() as session:
        doc = ensure_document(session, "https://example.org/call")
        associate(session, oid, doc, root=True)
        persist(session, doc, b"Full source conditions remain here.", "text/plain",
                Parsed(text="Incomplete old extraction", status="partial_text"), stamp=old)
        sha, due = doc.current_sha256, doc.next_check_at
    result = reextract_documents(factory, issues_only=True)
    assert result == {"reextracted": 1, "changed": 1}
    with factory() as session:
        doc = session.get(Document, digest("https://example.org/call"))
        assert doc.current_sha256 == sha and doc.last_success_at == old and doc.checked_at == old
        assert doc.next_check_at == due and doc.attempts == 1
        blob = session.get(DocumentBlob, sha)
        assert gzip.decompress(blob.original_gzip) == b"Full source conditions remain here."
        assert blob.text == "Full source conditions remain here." and doc.extraction_status == "extracted"
        assert session.get(DocumentVersion, (doc.id, sha)).last_seen_at == old


def test_reextraction_can_target_a_document_without_touching_other_derivatives(database):
    _, _, factory = database
    with factory.begin() as session:
        selected = ensure_document(session, "https://example.org/selected")
        other = ensure_document(session, "https://example.org/other")
        persist(session, selected, b"Correct selected full text.", "text/plain", Parsed(text="Old selected text"))
        persist(session, other, b"Other full text.", "text/plain", Parsed(text="Existing other derivative"))
        sid, other_sha = selected.id, other.current_sha256
    result = reextract_documents(factory, document_ids=[sid])
    assert result == {"reextracted": 1, "changed": 1}
    with factory() as session:
        assert session.get(DocumentBlob, session.get(Document, sid).current_sha256).text == "Correct selected full text."
        assert session.get(DocumentBlob, other_sha).text == "Existing other derivative"


def test_reextraction_does_not_hide_missing_publisher_conditions(database):
    _, _, factory = database
    oid = add_opportunity(factory)
    with factory.begin() as session:
        doc = ensure_document(session, "https://example.org/call", "eu_source")
        associate(session, oid, doc, root=True)
        persist(session, doc, b'{"documents":[{"metadata":{"identifier":["TOPIC-1"]}}]}',
                "application/json", Parsed(text="Catalogue metadata only", status="partial_text",
                flags=["full_eu_conditions_not_present_in_source_entry"]))
    reextract_documents(factory, issues_only=True)
    with factory() as session:
        doc = session.get(Document, digest("https://example.org/call"))
        assert doc.extraction_status == "partial_text"
        assert "full_eu_conditions_not_present_in_source_entry" in json.loads(session.get(DocumentBlob, doc.current_sha256).flags_json)


def test_missing_eu_text_follows_published_detail_url_without_duplicate_links():
    from funding.document_parsers import Link
    from funding.documents import mark_eu_completeness
    url = "https://example.org/data/topic.json"
    raw = {"documents": [{"url": url, "metadata": {"url": [url], "description": []}}]}
    parsed = Parsed(text="Metadata only", links=[Link(url)])
    mark_eu_completeness(raw, parsed, "https://example.org/topic")
    assert parsed.status == "partial_text" and len(parsed.links) == 1
    assert parsed.links[0].follow and parsed.links[0].role == "source_detail_fallback"
    raw["documents"][0]["metadata"]["topicConditions"] = ["Full published conditions"]
    complete = Parsed(text="Full conditions", links=[Link(url)])
    mark_eu_completeness(raw, complete, "https://example.org/topic")
    assert complete.status == "extracted" and not complete.links[0].follow


def test_missing_faq_answer_stays_partial_on_direct_api_refresh(database):
    from funding.documents import mark_faq_completeness
    cfg, _, _ = database
    raw = {"metadata": {"nid": ["12125"], "question": ["Full question?"], "answer": ["<p>&nbsp;</p>"]}}
    parsed = Parsed(text="Published question without answer")
    mark_faq_completeness(raw, parsed, "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/support/faq/12125")
    assert parsed.status == "partial_text" and len(parsed.links) == 1
    assert parsed.links[0].parser == "eu_faq_detail"
    def transport(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        assert str(request.url) == parsed.links[0].url
        return httpx.Response(200, json=raw)
    def client_factory(config, _):
        return PublicClient(config, ["api.tech.ec.europa.eu"], transport=httpx.MockTransport(transport))
    result = fetch_document(cfg, {"parser": "eu_faq_detail", "url": parsed.links[0].url,
                                 "etag": None, "last_modified": None}, client_factory)
    assert result["parsed"].status == "partial_text"
    assert not result["parsed"].links  # The fallback must not schedule itself.
    assert "full_faq_question_or_answer_not_published" in result["parsed"].flags


def test_portable_export_contains_full_text_bytes_and_safe_call_index(database, tmp_path):
    from funding.export import export_documents
    _, engine, factory = database
    oid = add_opportunity(factory)
    full_text = "Täydelliset ehdot. "*4000+"Viimeinen ehto."
    body = b"<script>untrusted source HTML</script>"
    with factory.begin() as session:
        session.get(Opportunity, oid).title = "<script>unsafe title</script>"
        doc = ensure_document(session, "https://example.org/rules")
        associate(session, oid, doc, root=True)
        persist(session, doc, body, "text/html", Parsed(text=full_text, status="partial_text",
                flags=["pages_need_visual_or_ocr_review:2", "ocr_text_requires_human_verification"]))
        sha = doc.current_sha256
    export_documents(engine, tmp_path)
    assert (tmp_path/f"documents/originals/{sha}.html").read_bytes() == body
    assert (tmp_path/f"documents/texts/{sha}.txt").read_text() == full_text
    index = (tmp_path/f"documents/calls/{oid}.html").read_text()
    assert "<script>unsafe title" not in index and "&lt;script&gt;unsafe title" in index
    assert f'href="../texts/{sha}.txt"' in index
    assert f'download href="../originals/{sha}.html"' in index
    assert "Tarkista alkuperäisestä sivut 2." in index and "Tekstiä on tunnistettu kuvista." in index
