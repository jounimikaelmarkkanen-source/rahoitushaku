"""Distinguish dated calls from reusable funding schemes; retain all v1 records."""
import sqlalchemy as sa
from alembic import op

from funding.schema_v1 import view_statements

revision = "0002"
down_revision = "0001"


def upgrade():
    op.add_column("opportunities", sa.Column("record_kind", sa.String(30), nullable=False, server_default="call"))
    op.create_index("ix_opportunities_record_kind", "opportunities", ["record_kind"])
    # SQL Server stores the expanded columns of SELECT * in view metadata.
    op.execute("DROP VIEW v_funding")
    op.execute(next(iter(view_statements(op.get_bind().dialect.name))))


def downgrade():
    raise RuntimeError("Destructive downgrade is disabled; restore a verified backup instead")
