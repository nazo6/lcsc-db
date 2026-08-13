"""remove scrape progress tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("scraped_seen_products")
    op.drop_table("scrape_progress")


def downgrade() -> None:
    op.create_table(
        "scrape_progress",
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("brand_id", sa.Integer(), nullable=False),
        sa.Column("keyword", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=True),
        sa.Column("scraped_count", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("category_id", "brand_id", "keyword"),
    )
    op.create_table(
        "scraped_seen_products",
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("product_id"),
    )
