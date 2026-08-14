"""Database manager, SQLModel tables, variants generator, and migrations."""

from lcsc_db.db.schema import CategoryRecord, ProductParamRecord, ProductRecord
from lcsc_db.db.session import LCSCDatabase
from lcsc_db.db.variants import (
    VARIANTS,
    compress_file,
    create_fts_only_variant,
    generate_all_variants,
    generate_variant,
)

__all__ = [
    "CategoryRecord",
    "LCSCDatabase",
    "ProductParamRecord",
    "ProductRecord",
    "VARIANTS",
    "compress_file",
    "create_fts_only_variant",
    "generate_all_variants",
    "generate_variant",
]
