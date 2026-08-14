"""SQLModel table models defining the SQLite database schema.

The schema is managed through Alembic migrations (see ``lcsc_db/migrations``).
These models are the source of truth for table structure and are registered
in ``SQLModel.metadata``.
"""

import json
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlmodel import Field, SQLModel

from lcsc_db.models import Category, Product


class CategoryRecord(SQLModel, table=True):
    __tablename__ = "categories"  # pyrefly: ignore[bad-override]

    id: int | None = Field(default=None, primary_key=True)
    parent_id: int | None = None
    name_en: str
    name_cn: str | None = None
    code: str | None = None

    @classmethod
    def from_category(cls, category: Category) -> "CategoryRecord":
        """Map an API ``Category`` to a record for the categories table."""
        return cls(
            id=category.category_id,
            parent_id=category.parent_id,
            name_en=category.name_en,
            name_cn=category.name_cn,
            code=category.code,
        )


class ProductRecord(SQLModel, table=True):
    __tablename__ = "products"  # pyrefly: ignore[bad-override]

    lcsc_number: str = Field(primary_key=True)
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
    jlcpcb_stock: int | None = Field(default=0)
    jlcpcb_price_ladder: str | None = None
    jlcpcb_library_type: str | None = None
    jlcpcb_extra: str | None = None
    jlcpcb_last_updated: datetime | None = None
    last_updated: datetime | None = Field(
        default=None,
        sa_column_kwargs={"server_default": text("CURRENT_TIMESTAMP")},
    )
    raw_json: str | None = None

    @classmethod
    def from_product(
        cls, product: Product, *, include_raw_json: bool = True
    ) -> "ProductRecord | None":
        """Map an API ``Product`` to a record for the products table.

        Returns ``None`` if the product lacks an LCSC number.
        """
        if not product.lcsc_number:
            return None

        data: dict[str, Any] = {
            "lcsc_number": product.lcsc_number,
            "mfr_part_number": product.mfr_part_number,
            "brand_id": product.brand_id,
            "brand_name": product.brand_name,
            "package": product.package,
            "description": product.description,
            "category_id": product.category_id,
            "first_category_name": product.first_category_name,
            "second_category_name": product.second_category_name,
            "third_category_name": product.third_category_name,
            "stock": product.stock or 0,
            "stock_sz": product.stock_sz or 0,
            "stock_js": product.stock_js or 0,
            "stock_hk": product.stock_hk or 0,
            "moq": product.moq or 1,
            "spq": product.spq or 1,
            "min_packet_number": product.min_packet_number,
            "min_packet_unit": product.min_packet_unit,
            "product_unit": product.product_unit,
            "product_arrange": product.product_arrange,
            "price_ladder": json.dumps(
                [pl.model_dump(by_alias=True) for pl in (product.price_ladder or [])],
                ensure_ascii=False,
            ),
            "pdf_url": product.pdf_url,
            "image_url": product.image_url,
            "product_images": json.dumps(product.product_images or [], ensure_ascii=False),
            "msl": product.msl,
            "eccn": product.eccn,
            "url": product.url,
            "is_rohs": 1 if product.is_rohs else 0,
            "is_hot": 1 if product.is_hot else 0,
            "is_reel": 1 if product.is_reel else 0,
            "reel_price": product.reel_price or 0.0,
            "is_sample": 1 if product.is_sample else 0,
            "is_discount": 1 if product.is_discount else 0,
            "is_pre_sale": 1 if product.is_pre_sale else 0,
            "jlcpcb_stock": product.jlcpcb_stock or 0,
            "jlcpcb_price_ladder": product.jlcpcb_price_ladder,
            "jlcpcb_library_type": product.jlcpcb_library_type,
            "jlcpcb_extra": product.jlcpcb_extra,
            "jlcpcb_last_updated": product.jlcpcb_last_updated,
        }
        if include_raw_json:
            data["raw_json"] = json.dumps(
                product.model_dump(mode="json", by_alias=True, exclude_none=True),
                ensure_ascii=False,
            )
        return cls(**data)


class ProductParamRecord(SQLModel, table=True):
    __tablename__ = "product_params"  # pyrefly: ignore[bad-override]

    id: int | None = Field(default=None, primary_key=True)
    lcsc_number: str | None = Field(default=None, foreign_key="products.lcsc_number", index=True)
    param_name: str | None = None
    param_value: str | None = None

