"""Keep coverage metadata separate from large originals for efficient filtering."""
import sqlalchemy as sa
from alembic import op

from funding.schema_v5_views import view_statements

revision = "0005"
down_revision = "0004"

def upgrade():
    dialect=op.get_bind().dialect.name
    op.add_column("documents",sa.Column("extraction_status",sa.String(40),nullable=False,server_default="not_extracted"))
    op.create_index("ix_documents_current_sha256","documents",["current_sha256"])
    op.execute("UPDATE documents SET extraction_status=COALESCE((SELECT b.extraction_status FROM document_blobs b WHERE b.sha256=documents.current_sha256),'not_extracted')")
    if dialect == "mssql":
        for sql in view_statements(dialect):
            op.execute(sql.replace("CREATE VIEW", "CREATE OR ALTER VIEW",1))
    else:
        for name in ("v_funding", "v_funding_documents", "v_document_coverage", "v_funding_tags", "v_source_health"):
            op.execute("DROP VIEW "+name)
        for sql in view_statements(dialect):
            op.execute(sql)

def downgrade():
    raise RuntimeError("Destructive downgrade is disabled; restore a verified backup instead")
