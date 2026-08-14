"""LCSC Product Database package."""

from lcsc_db.api import LCSCApi, LCSCApiConfig, LCSCApiError
from lcsc_db.db import LCSCDatabase
from lcsc_db.models import (
    CatalogEntry,
    CatalogListResult,
    Category,
    Manufacturer,
    ParamGroupResult,
    PriceLadder,
    Product,
    ProductParam,
    ProductQueryResult,
)
from lcsc_db.schema import (
    CategoryRecord,
    ProductParamRecord,
    ProductRecord,
)
from lcsc_db.scraper import LCSCScraper, ScraperConfig
from lcsc_db.variants import (
    VARIANTS,
    compress_file,
    create_fts_only_variant,
    generate_all_variants,
    generate_variant,
)

__all__ = [
    "CatalogEntry",
    "CatalogListResult",
    "Category",
    "CategoryRecord",
    "LCSCApi",
    "LCSCApiConfig",
    "LCSCApiError",
    "LCSCDatabase",
    "LCSCScraper",
    "Manufacturer",
    "ParamGroupResult",
    "PriceLadder",
    "Product",
    "ProductParam",
    "ProductParamRecord",
    "ProductQueryResult",
    "ProductRecord",
    "ScraperConfig",
    "VARIANTS",
    "compress_file",
    "create_fts_only_variant",
    "generate_all_variants",
    "generate_variant",
]
__version__ = "0.1.0"
