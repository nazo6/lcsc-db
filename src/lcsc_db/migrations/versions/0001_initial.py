"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-08-13 10:20:31.688027

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("name_en", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name_cn", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("code", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "scrape_progress",
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("brand_id", sa.Integer(), nullable=False),
        sa.Column("keyword", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
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
    op.create_table(
        "products",
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("lcsc_number", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("mfr_part_number", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("brand_id", sa.Integer(), nullable=True),
        sa.Column("brand_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("package", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("first_category_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("second_category_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("third_category_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("stock", sa.Integer(), nullable=True),
        sa.Column("stock_sz", sa.Integer(), nullable=True),
        sa.Column("stock_js", sa.Integer(), nullable=True),
        sa.Column("stock_hk", sa.Integer(), nullable=True),
        sa.Column("moq", sa.Integer(), nullable=True),
        sa.Column("spq", sa.Integer(), nullable=True),
        sa.Column("min_packet_number", sa.Integer(), nullable=True),
        sa.Column("min_packet_unit", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("product_unit", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("product_arrange", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("price_ladder", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("pdf_url", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("image_url", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("product_images", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("msl", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("eccn", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("url", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("is_rohs", sa.Integer(), nullable=True),
        sa.Column("is_hot", sa.Integer(), nullable=True),
        sa.Column("is_reel", sa.Integer(), nullable=True),
        sa.Column("reel_price", sa.Float(), nullable=True),
        sa.Column("is_sample", sa.Integer(), nullable=True),
        sa.Column("is_discount", sa.Integer(), nullable=True),
        sa.Column("is_pre_sale", sa.Integer(), nullable=True),
        sa.Column(
            "last_updated",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column("raw_json", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.PrimaryKeyConstraint("product_id"),
    )
    op.create_index("ix_products_lcsc_number", "products", ["lcsc_number"], unique=True)
    op.create_index("ix_products_mfr_part_number", "products", ["mfr_part_number"], unique=False)
    op.create_index("ix_products_category_id", "products", ["category_id"], unique=False)
    op.create_table(
        "product_params",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("param_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("param_value", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.product_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_product_params_product_id", "product_params", ["product_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_product_params_product_id", table_name="product_params")
    op.drop_table("product_params")
    op.drop_index("ix_products_lcsc_number", table_name="products")
    op.drop_index("ix_products_mfr_part_number", table_name="products")
    op.drop_index("ix_products_category_id", table_name="products")
    op.drop_table("products")
    op.drop_table("scraped_seen_products")
    op.drop_table("scrape_progress")
    op.drop_table("categories")
