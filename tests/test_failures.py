from sqlalchemy import func, select

from funding.adapters import Batch
from funding.collector import collect, upsert
from funding.domain import Record
from funding.models import Opportunity, Run, Source


def test_partial_source_failure_preserves_previous_data_and_marks_health(database, monkeypatch):
    cfg, _, factory = database
    record = Record(external_id="x", canonical_url="https://example.org/x", title="Test funding")
    with factory.begin() as s:
        upsert(s, "test", record, {})
    def broken(client, config):
        yield Batch(items=[(record, {})], expected=2)
        raise ValueError("Second page failed")
    monkeypatch.setitem(__import__("funding.collector", fromlist=["ADAPTERS"]).ADAPTERS, "haeavustuksia", broken)
    class Client:
        def __init__(self, *a):
            pass
        def close(self):
            pass
    result = collect(factory, cfg, ["test"], Client)
    assert result[0]["status"] == "partial"
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(Opportunity)) == 1
        assert s.get(Source, "test").last_success_at is None
        assert s.scalar(select(Run)).expected == 2
