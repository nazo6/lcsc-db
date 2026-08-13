"""Unit tests for LCSCDatabase handling SQLite storage, lossless raw_json, and FTS5 search."""

import json

import pytest
from sqlmodel import Session, select, text

from lcsc_db.db import LCSCDatabase
from lcsc_db.models import Product
from lcsc_db.schema import ProductRecord, ScrapedSeenProductRecord


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_lcsc.sqlite3"
    db = LCSCDatabase(str(db_file))
    yield db
    db.close()


def _table_columns(db, table_name):
    with db.engine.connect() as conn:
        return [row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table_name});")]


def test_db_schema_options(temp_db):
    temp_db.init_schema(enable_fts=True)

    cols = _table_columns(temp_db, "products")
    assert "raw_json" in cols
    assert "moq" in cols
    assert "spq" in cols
    assert "stock_sz" in cols

    with temp_db.engine.connect() as conn:
        fts = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='products_fts';"
        ).first()
    assert fts is not None


def test_db_schema_without_fts(tmp_path):
    db_file = tmp_path / "test_no_raw.sqlite3"
    db = LCSCDatabase(str(db_file))
    db.init_schema(enable_fts=False)

    cols = _table_columns(db, "products")
    assert "raw_json" in cols

    with db.engine.connect() as conn:
        fts = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='products_fts';"
        ).first()
    assert fts is None
    db.close()


def test_upsert_products_lossless_and_fts(temp_db):
    temp_db.init_schema(enable_fts=True)

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

    with Session(temp_db.engine) as session:
        row = session.exec(
            select(ProductRecord).where(ProductRecord.product_id == 107087)
        ).one()
    assert row.lcsc_number == "C105872"
    assert row.mfr_part_number == "RC0402FR-075K1L"
    assert row.moq == 100
    assert row.spq == 100

    raw_json_data = json.loads(row.raw_json)
    assert raw_json_data["productId"] == 107087
    assert raw_json_data["productCode"] == "C105872"

    # Test FTS5 Search
    with Session(temp_db.engine) as session:
        fts_row = session.execute(
            text("SELECT * FROM products_fts WHERE products_fts MATCH 'RC0402FR';")
        ).first()
    assert fts_row is not None
    assert fts_row[0] == "C105872"


def test_raw_json_null_when_disabled(temp_db):
    temp_db.init_schema()

    p = {"productId": 201, "productCode": "C201", "productModel": "M201"}
    temp_db.upsert_products([Product.model_validate(p)], include_raw_json=False)

    with Session(temp_db.engine) as session:
        row = session.exec(
            select(ProductRecord).where(ProductRecord.product_id == 201)
        ).one()
    assert row.raw_json is None


def test_db_progress_tracking(temp_db):
    temp_db.init_schema()

    assert not temp_db.is_query_completed(101, 5, "a")
    assert not temp_db.has_incomplete_progress()

    temp_db.mark_query_completed(101, brand_id=5, keyword="a", total_rows=100, scraped_count=100)
    assert temp_db.is_query_completed(101, 5, "a")
    assert temp_db.has_incomplete_progress()

    temp_db.record_seen_products({1001, 1002})
    with Session(temp_db.engine) as session:
        seen = session.exec(select(ScrapedSeenProductRecord)).all()
    assert len(seen) == 2

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

    with Session(temp_db.engine) as session:
        stock_101 = session.exec(
            select(ProductRecord.stock).where(ProductRecord.product_id == 101)
        ).one()
        stock_102 = session.exec(
            select(ProductRecord.stock).where(ProductRecord.product_id == 102)
        ).one()
    assert stock_101 == 50
    assert stock_102 == 0
