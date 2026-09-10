"""Reprocess stored public EU documents after parser fixes, without network requests."""
import json
from uuid import uuid4

from sqlalchemy import delete, select

from funding.adapters import eu_record, preferred_eu_variant
from funding.collector import acquire, heartbeat, upsert
from funding.db import make_engine, sessions
from funding.models import Lease, SourceItem
from funding.settings import settings


def main():
    factory = sessions(make_engine(settings()))
    owner = str(uuid4())
    if not acquire(factory, "collector", owner):
        raise RuntimeError("Stop the collector before reprocessing")
    changed, seen, after = 0, 0, ""
    try:
        while True:
            with factory.begin() as s:
                heartbeat(s, owner)
                items = s.scalars(select(SourceItem).where(SourceItem.source_id == "eu-funding", SourceItem.id > after).order_by(SourceItem.id).limit(100)).all()
                if not items:
                    break
                for item in items:
                    raw = json.loads(item.raw_json)
                    variants = [(eu_record(doc), doc) for doc in raw["documents"]]
                    record = preferred_eu_variant(variants)
                    changed += int(upsert(s, "eu-funding", record, raw))
                    seen += 1
                after = items[-1].id
    finally:
        with factory.begin() as s:
            s.execute(delete(Lease).where(Lease.name == "collector", Lease.owner == owner))
    print(json.dumps({"reprocessed": seen, "changed": changed}))


if __name__ == "__main__":
    main()
