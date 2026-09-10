from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from funding.settings import Settings


def make_engine(cfg: Settings):
    if cfg.azure_sql_server:
        url = URL.create(
            "mssql+pyodbc", host=cfg.azure_sql_server, database=cfg.azure_sql_database,
            query={"driver": "ODBC Driver 18 for SQL Server", "Encrypt": "yes", "TrustServerCertificate": "no"},
        )
        engine = create_engine(url, pool_pre_ping=True, pool_recycle=1200, deprecate_large_types=True)
        import struct

        from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

        credential = (
            ManagedIdentityCredential(client_id=cfg.managed_identity_client_id)
            if cfg.managed_identity_client_id else DefaultAzureCredential()
        )

        @event.listens_for(engine, "do_connect")
        def access_token(dialect, conn_rec, cargs, cparams):
            cargs[0] = cargs[0].replace(";Trusted_Connection=Yes", "")
            token = credential.get_token("https://database.windows.net/.default").token.encode("utf-16-le")
            cparams["attrs_before"] = {1256: struct.pack(f"<I{len(token)}s", len(token), token)}

        return engine
    url = cfg.database_url
    if url.startswith("sqlite:///") and url != "sqlite:///:memory:":
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, pool_pre_ping=True, **({"deprecate_large_types": True} if url.startswith("mssql") else {}), **(
        {"connect_args": {"check_same_thread": False, "timeout": 30}} if url.startswith("sqlite") else {}
    ))
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def sqlite_settings(connection, _):
            connection.create_function("lower", 1, lambda value: value.casefold() if value is not None else None, deterministic=True)
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
    return engine


def sessions(engine):
    return sessionmaker(engine, expire_on_commit=False)
