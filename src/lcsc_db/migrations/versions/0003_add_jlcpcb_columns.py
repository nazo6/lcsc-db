"""add jlcpcb columns to products table

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("products") as batch_op:
        batch_op.add_column(sa.Column("jlcpcb_stock", sa.Integer(), nullable=True, server_default="0"))
        batch_op.add_column(sa.Column("jlcpcb_price_ladder", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("jlcpcb_library_type", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("jlcpcb_extra", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("jlcpcb_last_updated", sa.DateTime(), nullable=True))

    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if inspector.has_table("products_fts"):
        op.execute("DROP TABLE products_fts")
        op.execute("""
            CREATE VIRTUAL TABLE products_fts USING fts5(
                lcsc_number,
                mfr_part_number,
                brand_name,
                package,
                description,
                first_category_name,
                second_category_name,
                tokenize="trigram",
                content='products',
                content_rowid='product_id'
            )
        """)


def downgrade() -> None:
    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_column("jlcpcb_last_updated")
        batch_op.drop_column("jlcpcb_extra")
        batch_op.drop_column("jlcpcb_library_type")
        batch_op.drop_column("jlcpcb_price_ladder")
        batch_op.drop_column("jlcpcb_stock")

    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if inspector.has_table("products_fts"):
        op.execute("DROP TABLE products_fts")
        op.execute("""
            CREATE VIRTUAL TABLE products_fts USING fts5(
                lcsc_number,
                mfr_part_number,
                brand_name,
                package,
                description,
                content='products',
                content_rowid='product_id'
            )
        """)
