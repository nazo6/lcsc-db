"""Unit tests for JLCPCB database sync and trigram search integration."""

import sqlite3
from pathlib import Path

import pytest
from sqlmodel import Session, select

from lcsc_db.db import LCSCDatabase
from lcsc_db.jlcpcb import import_cache_db
from lcsc_db.models import Product
from lcsc_db.schema import ProductRecord


@pytest.fixture
def mock_cache_db(tmp_path: Path) -> Path:
    """Create a mock cache.sqlite3 database matching kicad-jlcpcb-tools schema."""
    cache_path = tmp_path / "cache.sqlite3"
    conn = sqlite3.connect(cache_path)
    conn.execute("""
        CREATE TABLE categories (
            id INTEGER PRIMARY KEY,
            first TEXT NOT NULL,
            second TEXT NOT NULL
        );
    """)
    conn.execute("""
        CREATE TABLE manufacturers (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        );
    """)
    conn.execute("""
        CREATE TABLE components (
            lcsc INTEGER PRIMARY KEY,
            category_id INTEGER NOT NULL,
            mfr TEXT NOT NULL,
            package TEXT NOT NULL,
            joints INTEGER NOT NULL,
            manufacturer_id INTEGER NOT NULL,
            basic INTEGER NOT NULL,
            description TEXT NOT NULL,
            datasheet TEXT NOT NULL,
            stock INTEGER NOT NULL,
            price TEXT NOT NULL,
            last_update INTEGER NOT NULL,
            extra TEXT,
            flag INTEGER NOT NULL DEFAULT 0,
            last_on_stock INTEGER NOT NULL DEFAULT 0,
            preferred INTEGER NOT NULL DEFAULT 0
        );
    """)

    conn.execute("INSERT INTO categories VALUES (1, 'Capacitors', 'Multilayer Ceramic Capacitors MLCC - SMD/SMT');")
    conn.execute("INSERT INTO manufacturers VALUES (10, 'Sunlord');")
    conn.execute("""
        INSERT INTO components VALUES (
            89188, 1, '0603X105K160NT', '0603', 0, 10, 0,
            '0603 1uF 10% 16V Ceramic Capacitor', 'https://wmsc.lcsc.com/sample.pdf',
            15369, '[{"qFrom":1,"qTo":499,"price":0.0217}]', 1786342049,
            '{"minPurchaseNum":1,"leastPatchNumber":20}', 0, 1786342049, 1
        );
    """)
    conn.commit()
    conn.close()
    return cache_path


def test_jlcpcb_import_and_trigram_fts(tmp_path: Path, mock_cache_db: Path):
    target_db_file = tmp_path / "lcsc_test.sqlite3"
    with LCSCDatabase(str(target_db_file)) as db:
        db.init_schema(enable_fts=True)
        count = db.import_jlcpcb_cache(mock_cache_db)
        assert count == 1
        db.rebuild_fts()

        with Session(db.engine) as session:
            record = session.exec(select(ProductRecord).where(ProductRecord.product_id == 89188)).one()
            assert record.lcsc_number == "C89188"
            assert record.mfr_part_number == "0603X105K160NT"
            assert record.brand_name == "Sunlord"
            assert record.package == "0603"
            assert record.jlcpcb_stock == 15369
            assert record.jlcpcb_library_type == "Preferred"
            assert "minPurchaseNum" in (record.jlcpcb_extra or "")

        # Test Trigram FTS search with substring matching
        with db.engine.connect() as conn:
            row = conn.exec_driver_sql(
                "SELECT * FROM products_fts WHERE products_fts MATCH '0603';"
            ).first()
            assert row is not None
            assert row[0] == "C89188"


def test_property_priority_lcsc_overlay(tmp_path: Path, mock_cache_db: Path):
    target_db_file = tmp_path / "lcsc_overlay.sqlite3"
    with LCSCDatabase(str(target_db_file)) as db:
        db.init_schema(enable_fts=True)

        # 1. First, insert a product via LCSC scrape with detailed description
        lcsc_product = {
            "productId": 89188,
            "productCode": "C89188",
            "productModel": "0603X105K160NT",
            "brandNameEn": "Sunlord (Detailed)",
            "productIntroEn": "Detailed LCSC Description",
            "stockNumber": 5000,
        }
        db.upsert_products([Product.model_validate(lcsc_product)], include_raw_json=True)

        # 2. Import JLCPCB cache DB
        db.import_jlcpcb_cache(mock_cache_db)

        # 3. Verify LCSC properties remain preserved while JLCPCB stock/pricing fields are updated
        with Session(db.engine) as session:
            record = session.exec(select(ProductRecord).where(ProductRecord.product_id == 89188)).one()
            assert record.brand_name == "Sunlord (Detailed)"
            assert record.description == "Detailed LCSC Description"
            assert record.jlcpcb_stock == 15369
            assert record.stock == 5000
            assert record.jlcpcb_library_type == "Preferred"
