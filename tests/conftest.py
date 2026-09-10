import pytest

from funding.db import make_engine, sessions
from funding.domain import dump
from funding.models import Base, Source
from funding.settings import Settings
from funding.views import view_statements


@pytest.fixture
def database(tmp_path):
    cfg = Settings(database_url=f"sqlite:///{tmp_path}/test.db", min_request_interval=0)
    engine = make_engine(cfg)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for sql in view_statements("sqlite"):
            conn.exec_driver_sql(sql)
        conn.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32))")
        conn.exec_driver_sql("INSERT INTO alembic_version VALUES ('0001')")
    factory = sessions(engine)
    with factory.begin() as session:
        for source_id in ("test", "second", "manual"):
            config = {"id": source_id, "url": "https://example.org/calls", "allowed_hosts": ["example.org"], "adapter": "haeavustuksia"}
            session.add(Source(id=source_id, name=source_id, url=config["url"], adapter="haeavustuksia", category="test", coverage="test", owner="test", enabled=True, config_json=dump(config)))
    yield cfg, engine, factory
    engine.dispose()
