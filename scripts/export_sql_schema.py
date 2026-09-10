"""Produce a reviewable SQL Server/Azure SQL initial schema, without connecting."""
from pathlib import Path

from sqlalchemy import create_mock_engine

from funding.models import Base
from funding.views import view_statements

statements = []


def capture(sql, *args, **kwargs):
    statements.append(str(sql.compile(dialect=engine.dialect)).strip())


engine = create_mock_engine("mssql+pyodbc://", capture, deprecate_large_types=True)
Base.metadata.create_all(engine, checkfirst=False)
statements.extend(view_statements("mssql"))
statements.extend([
    "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)",
    "INSERT INTO alembic_version (version_num) VALUES ('0007')",
])
Path("infra/schema-current.sql").write_text("-- Schema revision 0007; use only for an empty database.\n-- Normally run alembic upgrade head instead.\n\n"+"\nGO\n\n".join(statements)+"\nGO\n", encoding="utf-8")
print(f"SQL Server dialect: {len(statements)} schema statements generated.")
