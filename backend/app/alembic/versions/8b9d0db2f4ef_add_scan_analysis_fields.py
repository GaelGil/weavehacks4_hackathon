"""add scan analysis fields

Revision ID: 8b9d0db2f4ef
Revises: ff34fd8ad50c
Create Date: 2026-06-07 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "8b9d0db2f4ef"
down_revision = "ff34fd8ad50c"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("scan", sa.Column("impersonated_brand", sa.String(length=255), nullable=True))
    op.add_column("scan", sa.Column("confidence_score", sa.Float(), nullable=True))
    op.add_column("scan", sa.Column("detected_text", sa.Text(), nullable=True))
    op.add_column("scan", sa.Column("detected_urls", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("scan", sa.Column("extracted_details", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("scan", sa.Column("similar_scams", sa.JSON(), nullable=False, server_default="[]"))
    op.alter_column("scan", "detected_urls", server_default=None)
    op.alter_column("scan", "extracted_details", server_default=None)
    op.alter_column("scan", "similar_scams", server_default=None)


def downgrade():
    op.drop_column("scan", "similar_scams")
    op.drop_column("scan", "extracted_details")
    op.drop_column("scan", "detected_urls")
    op.drop_column("scan", "detected_text")
    op.drop_column("scan", "confidence_score")
    op.drop_column("scan", "impersonated_brand")
