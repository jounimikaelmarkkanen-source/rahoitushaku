"""Expose per-link extraction quality even when multiple URLs share identical bytes."""
from alembic import op

revision = "0007"
down_revision = "0006"

SQL = """CREATE VIEW v_funding_documents AS SELECT od.*, d.url, d.final_url, d.title,
    d.state, d.parser, d.checked_at, d.last_success_at, d.http_status, d.error, d.current_sha256,
    b.media_type, b.byte_count, b.text AS full_text, d.extraction_status, b.flags_json, b.page_count
    FROM opportunity_documents od JOIN documents d ON od.document_id=d.id
    LEFT JOIN document_blobs b ON d.current_sha256=b.sha256"""


def upgrade():
    if op.get_bind().dialect.name == "mssql":
        op.execute(SQL.replace("CREATE VIEW", "CREATE OR ALTER VIEW", 1))
    else:
        op.execute("DROP VIEW v_funding_documents")
        op.execute(SQL)


def downgrade():
    raise RuntimeError("Destructive downgrade is disabled; restore a verified backup instead")
