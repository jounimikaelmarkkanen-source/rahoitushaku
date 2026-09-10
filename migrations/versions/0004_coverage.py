"""Show explicit coverage failures even while other documents are pending."""
from alembic import op

from funding.schema_v4_views import view_statements

revision = "0004"
down_revision = "0003"

def upgrade():
    for name in ("v_funding", "v_funding_documents", "v_document_coverage", "v_funding_tags", "v_source_health"):
        op.execute("DROP VIEW "+name)
    for sql in view_statements(op.get_bind().dialect.name):
        op.execute(sql)

def downgrade():
    raise RuntimeError("Destructive downgrade is disabled; restore a verified backup instead")
