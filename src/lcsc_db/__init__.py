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
from lcsc_db.scraper import LCSCScraper, ScraperConfig

__all__ = [
    "CatalogEntry",
    "CatalogListResult",
    "Category",
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
    "ProductQueryResult",
    "ScraperConfig",
]
__version__ = "0.1.0"
