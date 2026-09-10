"""Archive full funding terms, attachments, versions and coverage."""
from alembic import op

from funding.schema_v3_documents import metadata, view_statements

revision = "0003"
down_revision = "0002"

def upgrade():
    bind = op.get_bind()
    tables = [t for t in metadata.sorted_tables if t.name != "opportunities"]
    metadata.create_all(bind, tables=tables)
    for name in ("v_funding", "v_funding_tags", "v_source_health"):
        op.execute("DROP VIEW "+name)
    for sql in view_statements(bind.dialect.name):
        op.execute(sql)

def downgrade():
    raise RuntimeError("Destructive downgrade is disabled; restore a verified backup instead")
