"""Funding registry schema v1."""
from alembic import op

from funding.schema_v1 import metadata, view_statements

revision = "0001"
down_revision = None


def upgrade():
    bind = op.get_bind()
    metadata.create_all(bind)
    for statement in view_statements(bind.dialect.name):
        op.execute(statement)


def downgrade():
    raise RuntimeError("Destructive downgrade is disabled; restore a verified backup instead")
