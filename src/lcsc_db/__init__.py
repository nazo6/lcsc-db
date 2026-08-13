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
    FTS_DDL,
    ProductParamRecord,
    ProductRecord,
)
from lcsc_db.scraper import LCSCScraper, ScraperConfig

__all__ = [
    "CatalogEntry",
    "CatalogListResult",
    "Category",
    "CategoryRecord",
    "FTS_DDL",
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
]
__version__ = "0.1.0"
