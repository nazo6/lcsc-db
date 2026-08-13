"""SQLModel table models defining the SQLite database schema.

The schema is managed through Alembic migrations (see ``lcsc_db/migrations``).
These models are the source of truth for table structure and are registered
in ``SQLModel.metadata``.
"""

from datetime import datetime

from sqlalchemy import text
from sqlmodel import Field, SQLModel


class CategoryRecord(SQLModel, table=True):
    __tablename__ = "categories"

    id: int | None = Field(default=None, primary_key=True)
    parent_id: int | None = None
    name_en: str
    name_cn: str | None = None
    code: str | None = None


class ProductRecord(SQLModel, table=True):
    __tablename__ = "products"

    product_id: int | None = Field(default=None, primary_key=True)
    lcsc_number: str = Field(unique=True, index=True)
    mfr_part_number: str = Field(index=True)
    brand_id: int | None = None
    brand_name: str | None = None
    package: str | None = None
    description: str | None = None
    category_id: int | None = Field(default=None, foreign_key="categories.id", index=True)
    first_category_name: str | None = None
    second_category_name: str | None = None
    third_category_name: str | None = None
    stock: int | None = Field(default=0)
    stock_sz: int | None = Field(default=0)
    stock_js: int | None = Field(default=0)
    stock_hk: int | None = Field(default=0)
    moq: int | None = Field(default=1)
    spq: int | None = Field(default=1)
    min_packet_number: int | None = None
    min_packet_unit: str | None = None
    product_unit: str | None = None
    product_arrange: str | None = None
    price_ladder: str | None = None
    pdf_url: str | None = None
    image_url: str | None = None
    product_images: str | None = None
    msl: str | None = None
    eccn: str | None = None
    url: str | None = None
    is_rohs: int | None = Field(default=0)
    is_hot: int | None = Field(default=0)
    is_reel: int | None = Field(default=0)
    reel_price: float | None = Field(default=0.0)
    is_sample: int | None = Field(default=0)
    is_discount: int | None = Field(default=0)
    is_pre_sale: int | None = Field(default=0)
    last_updated: datetime | None = Field(
        default=None,
        sa_column_kwargs={"server_default": text("CURRENT_TIMESTAMP")},
    )
    raw_json: str | None = None


class ProductParamRecord(SQLModel, table=True):
    __tablename__ = "product_params"

    id: int | None = Field(default=None, primary_key=True)
    product_id: int | None = Field(default=None, foreign_key="products.product_id", index=True)
    param_name: str | None = None
    param_value: str | None = None


class ScrapeProgressRecord(SQLModel, table=True):
    __tablename__ = "scrape_progress"

    category_id: int = Field(primary_key=True)
    brand_id: int = Field(default=0, primary_key=True)
    keyword: str = Field(default="", primary_key=True)
    status: str = Field(default="completed")
    total_rows: int | None = Field(default=0)
    scraped_count: int | None = Field(default=0)
    updated_at: datetime | None = Field(
        default=None,
        sa_column_kwargs={"server_default": text("CURRENT_TIMESTAMP")},
    )


class ScrapedSeenProductRecord(SQLModel, table=True):
    __tablename__ = "scraped_seen_products"

    product_id: int = Field(primary_key=True)


FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS products_fts USING fts5(
    lcsc_number,
    mfr_part_number,
    brand_name,
    package,
    description,
    content='products',
    content_rowid='product_id'
);
"""
