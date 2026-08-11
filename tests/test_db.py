"""Unit tests for LCSCDatabase handling SQLite storage, lossless raw_json, and FTS5 search."""

import json
import sqlite3
import pytest

from lcsc_db.db import LCSCDatabase


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

    temp_db.upsert_products([sample_product], include_raw_json=True)
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
