"""Unit tests for LCSCDatabase handling SQLite storage, lossless raw_json, and FTS5 search."""

import json
import sqlite3
import pytest

from lcsc_db.db import LCSCDatabase
from lcsc_db.models import Product


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_lcsc.sqlite3"
    db = LCSCDatabase(str(db_file))
    yield db
    db.close()


def test_db_schema_options(temp_db):
    # Test with include_raw_json=True and enable_fts=True
    temp_db.init_schema(include_raw_json=True, enable_fts=True)

    cursor = temp_db.conn.cursor()
    cursor.execute("PRAGMA table_info(products);")
    cols = [row[1] for row in cursor.fetchall()]
    assert "raw_json" in cols
    assert "moq" in cols
    assert "spq" in cols
    assert "stock_sz" in cols

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='products_fts';")
    assert cursor.fetchone() is not None


def test_db_schema_without_raw_json(tmp_path):
    db_file = tmp_path / "test_no_raw.sqlite3"
    db = LCSCDatabase(str(db_file))
    db.init_schema(include_raw_json=False, enable_fts=False)

    cursor = db.conn.cursor()
    cursor.execute("PRAGMA table_info(products);")
    cols = [row[1] for row in cursor.fetchall()]
    assert "raw_json" not in cols

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='products_fts';")
    assert cursor.fetchone() is None
    db.close()


def test_upsert_products_lossless_and_fts(temp_db):
    temp_db.init_schema(include_raw_json=True, enable_fts=True)

    sample_product = {
        "productId": 107087,
        "productCode": "C105872",
        "productModel": "RC0402FR-075K1L",
        "brandId": 396,
        "brandNameEn": "YAGEO",
        "encapStandard": "0402",
        "productIntroEn": "5.1kΩ Thick Film Resistor",
        "catalogId": 1199,
        "stockNumber": 2168800,
        "stockSz": 2168800,
        "stockJs": 0,
        "wmStockHk": 0,
        "minBuyNumber": 100,
        "split": 100,
        "productPriceList": [{"ladder": 100, "usdPrice": 0.0054}],
        "pdfUrl": "https://datasheet.lcsc.com/sample.pdf",
        "productImageUrl": "https://assets.lcsc.com/sample.jpg",
        "paramVOList": [
            {"paramNameEn": "Resistance", "paramValueEn": "5.1kΩ"},
            {"paramNameEn": "Tolerance", "paramValueEn": "±1%"},
        ],
        "isEnvironment": True,
        "isHot": True,
    }

    temp_db.upsert_products([Product.model_validate(sample_product)], include_raw_json=True)
    temp_db.rebuild_fts()

    cursor = temp_db.conn.cursor()
    cursor.execute("SELECT * FROM products WHERE product_id = 107087;")
    row = cursor.fetchone()
    assert row is not None
    assert row["lcsc_number"] == "C105872"
    assert row["mfr_part_number"] == "RC0402FR-075K1L"
    assert row["moq"] == 100
    assert row["spq"] == 100

    raw_json_data = json.loads(row["raw_json"])
    assert raw_json_data["productId"] == 107087
    assert raw_json_data["productCode"] == "C105872"

    # Test FTS5 Search
    cursor.execute("SELECT * FROM products_fts WHERE products_fts MATCH 'RC0402FR';")
    fts_row = cursor.fetchone()
    assert fts_row is not None
    assert fts_row["lcsc_number"] == "C105872"


def test_db_progress_tracking(temp_db):
    temp_db.init_schema()

    assert not temp_db.is_query_completed(101, 5, "a")
    assert not temp_db.has_incomplete_progress()

    temp_db.mark_query_completed(101, brand_id=5, keyword="a", total_rows=100, scraped_count=100)
    assert temp_db.is_query_completed(101, 5, "a")
    assert temp_db.has_incomplete_progress()

    temp_db.record_seen_products({1001, 1002})
    cursor = temp_db.conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM scraped_seen_products;")
    assert cursor.fetchone()[0] == 2

    temp_db.clear_scrape_progress()
    assert not temp_db.has_incomplete_progress()
    assert not temp_db.is_query_completed(101, 5, "a")


def test_mark_unseen_stock_zero_from_db(temp_db):
    temp_db.init_schema()

    p1 = {"productId": 101, "productCode": "C101", "productModel": "M101", "stockNumber": 50}
    p2 = {"productId": 102, "productCode": "C102", "productModel": "M102", "stockNumber": 50}
    temp_db.upsert_products([Product.model_validate(p) for p in [p1, p2]])

    # Only record 101 as seen
    temp_db.record_seen_products({101})
    updated_rows = temp_db.mark_unseen_stock_zero_from_db()
    assert updated_rows == 1

    cursor = temp_db.conn.cursor()
    cursor.execute("SELECT stock FROM products WHERE product_id = 101;")
    assert cursor.fetchone()["stock"] == 50

    cursor.execute("SELECT stock FROM products WHERE product_id = 102;")
    assert cursor.fetchone()["stock"] == 0

