import gzip
import json
from pathlib import Path

import httpx
import pytest

from funding.adapters import eu, eu_record, eura_data, eura_record, hae, hae_record, preferred_eu_variant
from funding.http import PublicClient
from funding.settings import Settings


def test_public_http_gzip_is_decoded_once():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, content=gzip.compress(b'{"ok":true}'), headers={"Content-Encoding": "gzip"})
    client = PublicClient(Settings(min_request_interval=0), ["example.org"], transport=httpx.MockTransport(handler))
    assert client.request("GET", "https://example.org/calls").json() == {"ok": True}
    client.close()


def test_disallowed_robots_and_redirect_hosts_are_not_bypassed():
    client = PublicClient(Settings(min_request_interval=0), ["example.org"], transport=httpx.MockTransport(lambda r: httpx.Response(200, text="User-agent: *\nDisallow: /calls")))
    with pytest.raises(PermissionError):
        client.request("GET", "https://example.org/calls")
    with pytest.raises(ValueError):
        client.request("GET", "https://169.254.169.254/metadata")


def test_hae_checks_pagination_and_local_dates():
    row = {"hakuasianAsianumero": "test", "nimi": {"fi": "Testihaku"}, "hakuAlkaaDateTimeUtc": "2026-09-08T21:00:00Z", "hakuPaattyyDateTimeUtc": "2026-09-30T20:59:00Z"}
    record = hae_record(row)
    assert str(record.opens_on) == "2026-09-09"
    class Client:
        def request(self, *args, **kwargs):
            return httpx.Response(200, json={"totalCount": 2, "pageCount": 1, "hakuilmoitukset": [row]})
    with pytest.raises(ValueError, match="count mismatch"):
        list(hae(Client(), {"url": "https://example.org"}))


def test_eura_schema_drift_fails_loudly():
    with pytest.raises(ValueError, match="not found"):
        eura_data("<html>Temporarily unavailable</html>")


def test_eu_refuses_faq_as_funding_call():
    with pytest.raises(ValueError):
        eu_record({"metadata": {"type": ["2"], "identifier": ["FAQ"]}})


def test_real_contract_fixtures():
    base = Path("tests/fixtures")
    assert hae_record(json.loads((base/"hae.json").read_text())).external_id
    data = json.loads((base/"eura.json").read_text())
    assert eura_record(data["row"], data["codes"]).title
    assert eu_record(json.loads((base/"eu.json").read_text())).programme == "HORIZON"


def test_cascade_calls_have_their_own_identity_even_without_parent_identifier():
    a = eu_record({"metadata": {"type": ["8"], "callccm2Id": ["123"], "caName": ["First call"]}})
    b = eu_record({"metadata": {"type": ["8"], "callccm2Id": ["456"], "caName": ["Second call"]}})
    assert a.external_id != b.external_id
    assert a.canonical_url.endswith("competitive-calls-cs/123")


def test_old_eu_mirror_cannot_extend_current_deadline():
    older = {"metadata": {"type": ["1"], "identifier": ["TEST-1"], "title": ["Call"], "deadlineDate": ["2030-01-01"], "esDA_QueueDate": ["2026-01-01"], "DATASOURCE": ["SEDIA"]}}
    newer = {"metadata": {**older["metadata"], "deadlineDate": ["2026-09-30"], "esDA_QueueDate": ["2026-02-01"]}}
    chosen = preferred_eu_variant([(eu_record(older), older), (eu_record(newer), newer)])
    assert chosen.deadlines[0].original == "2026-09-30"
    assert len(chosen.deadlines) == 1
    assert "conflicting_source_deadlines" in chosen.quality_flags


def test_eu_partitions_beyond_search_window_and_keeps_undated_records():
    # 9,001 dated documents force recursive partitioning; page 201 must never be requested.
    docs = []
    for count, start, identifier in [(5000, "2020-01-01T00:00:00Z", "OLD"), (4001, "2025-01-01T00:00:00Z", "NEW"), (1, None, "UNDATED")]:
        for i in range(count):
            meta = {"type": ["1"], "identifier": [identifier], "title": [identifier], "status": ["31094502"]}
            if start:
                meta["startDate"] = [start]
            docs.append({"reference": f"{identifier}-{i}", "metadata": meta})
    class Client:
        def request(self, *args, **kwargs):
            conditions = json.loads(kwargs["files"]["query"][1])["bool"]["must"][3:]
            selected = docs
            for cond in conditions:
                if "exists" in cond:
                    selected = [d for d in selected if "startDate" in d["metadata"]]
                elif "bool" in cond:
                    selected = [d for d in selected if "startDate" not in d["metadata"]]
                else:
                    for op, cutoff in cond["range"]["startDate"].items():
                        selected = [d for d in selected if (d["metadata"]["startDate"][0] < cutoff if op == "lt" else d["metadata"]["startDate"][0] >= cutoff)]
            page = kwargs["params"]["pageNumber"]
            assert page <= 180
            return httpx.Response(200, json={"totalResults": len(selected), "results": selected[(page-1)*50:page*50]})
    batches = list(eu(Client(), {"url": "https://example.org"}))
    assert {r.external_id for b in batches for r, _ in b.items} == {"OLD", "NEW", "UNDATED"}
    assert sum(len(raw["documents"]) for b in batches for _, raw in b.items) == 9002
    assert not any(b.rejected or b.warnings for b in batches)
