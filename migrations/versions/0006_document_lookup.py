"""Index reverse document-to-call lookups used by collection and content searches."""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_opportunity_documents_lookup", "opportunity_documents",
                    ["document_id", "active", "opportunity_id"])


def downgrade():
    op.drop_index("ix_opportunity_documents_lookup", table_name="opportunity_documents")
