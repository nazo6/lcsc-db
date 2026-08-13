"""Pydantic models for LCSC API responses and product data."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    """Base model accepting camelCase API keys while exposing snake_case attributes.

    Unknown fields are preserved so the raw API JSON can be reconstructed losslessly.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="allow",
    )


class PriceLadder(_CamelModel):
    ladder: int | None = None
    usd_price: float | None = None


class ProductParam(_CamelModel):
    param_name_en: str | None = None
    param_name: str | None = None
    param_value_en: str | None = None
    param_value: str | None = None

    @property
    def name(self) -> str:
        return self.param_name_en or self.param_name or ""

    @property
    def value(self) -> str:
        return self.param_value_en or self.param_value or ""


class Product(_CamelModel):
    """A single LCSC product, mapping API fields to database columns."""

    product_id: int | None = None
    lcsc_number: str = Field("", alias="productCode")
    mfr_part_number: str = Field("", alias="productModel")
    brand_id: int | None = None
    brand_name: str | None = Field(None, alias="brandNameEn")
    package: str | None = Field(None, alias="encapStandard")
    description: str | None = Field(None, alias="productIntroEn")
    catalog_id: int | None = None
    wm_catalog_id: int | None = None
    first_category_name: str | None = Field(None, alias="firstWmCatalogNameEn")
    second_category_name: str | None = Field(None, alias="secondWmCatalogNameEn")
    third_category_name: str | None = Field(None, alias="thirdWmCatalogNameEn")
    stock: int | None = Field(0, alias="stockNumber")
    stock_sz: int | None = 0
    stock_js: int | None = 0
    stock_hk: int | None = Field(0, alias="wmStockHk")
    moq: int | None = Field(1, alias="minBuyNumber")
    spq: int | None = Field(1, alias="split")
    min_packet_number: int | None = None
    min_packet_unit: str | None = None
    product_unit: str | None = None
    product_arrange: str | None = None
    price_ladder: list[PriceLadder] | None = Field(None, alias="productPriceList")
    pdf_url: str | None = None
    image_url: str | None = Field(None, alias="productImageUrl")
    product_images: list[Any] | None = None
    msl: str | None = Field(None, alias="moistureSensitivityLevel")
    eccn: str | None = None
    url: str | None = None
    is_rohs: bool | None = Field(False, alias="isEnvironment")
    is_hot: bool | None = False
    is_reel: bool | None = False
    reel_price: float | None = 0.0
    is_sample: bool | None = False
    is_discount: bool | None = False
    is_pre_sale: bool | None = False
    params: list[ProductParam] | None = Field(None, alias="paramVOList")

    @property
    def category_id(self) -> int | None:
        return self.catalog_id or self.wm_catalog_id


class Category(_CamelModel):
    """A node in the LCSC category tree."""

    category_id: int | None = None
    parent_id: int | None = None
    name_en: str = Field("", alias="categoryNameEn")
    name_cn: str | None = Field(None, alias="categoryNameCn")
    code: str | None = Field(None, alias="enCategoryCode")
    children: list["Category"] | None = Field(None, alias="childrenList")


class CatalogEntry(_CamelModel):
    """A leaf category entry from the catalog list endpoint."""

    catalog_id: int | None = None
    name_en: str | None = Field(None, alias="catalogNameEn")
    product_num: int = 0
    child_catelogs: list["CatalogEntry"] | None = Field(None)


class Manufacturer(_CamelModel):
    id: int
    name: str = ""

    @field_validator("id", mode="before")
    @classmethod
    def _coerce_id(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return int(v)
            except ValueError:
                return v
        return v


class ProductQueryResult(_CamelModel):
    data_list: list[Product] = Field(default_factory=list)
    total_row: int = 0
    curr_page: int = 1
    total_page: int = 0


class ParamGroupResult(_CamelModel):
    total_count: int = 0
    manufacturers: list[Manufacturer] = Field(default_factory=list, alias="Manufacturer")


class CatalogListResult(_CamelModel):
    catalog_list: list[CatalogEntry] = Field(default_factory=list)
