"""Integration and unit tests for LCSCScraper."""

import pytest
from unittest.mock import MagicMock

from lcsc_db.api import LCSCApi
from lcsc_db.db import LCSCDatabase
from lcsc_db.scraper import LCSCScraper


def test_scraper_options_and_run(tmp_path):
    db_file = tmp_path / "test_scraper.sqlite3"
    api = LCSCApi(delay_seconds=0.0)
    db = LCSCDatabase(str(db_file))

    scraper = LCSCScraper(
        api=api,
        db=db,
        instock_only=True,
        include_raw_json=True,
        enable_fts=True,
    )

    # Scrape category 51 with max 1 page
    count = scraper.run(target_category_id=51, max_pages_per_category=1)
    assert count >= 0

    cursor = db.conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM products;")
    total_in_db = cursor.fetchone()[0]
    assert total_in_db == count

    db.close()


def test_scraper_brand_partitioning_trigger(tmp_path):
    """Test that totalRow >= threshold triggers brand-based partitioning."""
    db_file = tmp_path / "test_brand_partition.sqlite3"
    api = LCSCApi(delay_seconds=0.0)
    db = LCSCDatabase(str(db_file))

    scraper = LCSCScraper(
        api=api,
        db=db,
        instock_only=True,
        partition_threshold=100,  # Lower threshold for testing
    )

    api.get_param_group = MagicMock(return_value={
        "Manufacturer": [
            {"id": "1001", "name": "BrandA"},
            {"id": "1002", "name": "BrandB"},
        ]
    })

    def mock_query(category_ids, brand_ids=None, page=1, page_size=100, instock_only=True, keyword=None):
        if brand_ids is None:
            return {"totalRow": 500, "totalPage": 5, "dataList": [{"productId": 1, "productCode": "C1"}]}
        return {"totalRow": 50, "totalPage": 1, "dataList": [{"productId": int(brand_ids[0] if isinstance(brand_ids, list) else brand_ids), "productCode": f"C{brand_ids}"}]}

    api.query_products = MagicMock(side_effect=mock_query)

    db.init_schema()
    count = scraper._scrape_category_query(cat_id=100, cat_path="Test Cat")

    # Should have fetched param group and queried products per brand
    assert api.get_param_group.call_count == 1
    assert api.query_products.call_count >= 3
    assert count == 2

    db.close()


def test_scraper_keyword_fallback_and_warning(tmp_path, caplog):
    """Test fallback to single-char keyword split when brand query >= threshold, and warning when brand+kw >= threshold."""
    db_file = tmp_path / "test_kw_fallback.sqlite3"
    api = LCSCApi(delay_seconds=0.0)
    db = LCSCDatabase(str(db_file))

    scraper = LCSCScraper(
        api=api,
        db=db,
        instock_only=True,
        partition_threshold=100,
    )

    # Return no manufacturers to test direct fallback to keyword
    api.get_param_group = MagicMock(return_value={"Manufacturer": []})

    def mock_query(category_ids, brand_ids=None, page=1, page_size=100, instock_only=True, keyword=None):
        # Always returns totalRow 200 >= threshold 100
        return {"totalRow": 200, "totalPage": 2, "dataList": [{"productId": 99, "productCode": "C99"}]}

    api.query_products = MagicMock(side_effect=mock_query)

    db.init_schema()
    import logging
    with caplog.at_level(logging.WARNING):
        count = scraper._scrape_category_query(cat_id=100, cat_path="Test Cat", brand_id=55, brand_name="BrandX")

    # Should have triggered 0-z keyword split (36 chars) and logged warnings for each char without infinite recursion
    assert "Exceeds max pagination capacity even after brand+keyword split" in caplog.text
    assert count > 0

    db.close()


def test_scraper_resume_and_skip(tmp_path):
    """Test that completed queries are skipped when resume=True."""
    db_file = tmp_path / "test_resume.sqlite3"
    api = LCSCApi(delay_seconds=0.0)
    db = LCSCDatabase(str(db_file))
    db.init_schema()

    api.get_category_tree = MagicMock(return_value=[
        {"categoryId": 51, "categoryNameEn": "Resistors", "childrenList": []},
        {"categoryId": 52, "categoryNameEn": "Capacitors", "childrenList": []},
    ])
    api.query_products = MagicMock(return_value={
        "totalRow": 1, "totalPage": 1, "dataList": [{"productId": 501, "productCode": "C501"}]
    })

    # Pre-mark Category 51 as completed in DB
    db.mark_query_completed(51, brand_id=0, keyword="", total_rows=1, scraped_count=1)

    scraper = LCSCScraper(api=api, db=db, resume=True)

    # Run scraper - should skip Cat 51 and process only Cat 52
    count = scraper.run()

    # Category 51 was skipped, Cat 52 was scraped
    assert count == 1
    assert api.query_products.call_count == 1
    # Verify query_products was called with category_ids=52
    assert api.query_products.call_args[1]["category_ids"] == 52

    db.close()


def test_scraper_max_duration(tmp_path):
    """Test that max_duration stops scraping gracefully and retains progress."""
    import time
    db_file = tmp_path / "test_duration.sqlite3"
    api = LCSCApi(delay_seconds=0.0)
    db = LCSCDatabase(str(db_file))

    api.get_category_tree = MagicMock(return_value=[
        {"categoryId": 1, "categoryNameEn": "Cat1", "childrenList": []},
        {"categoryId": 2, "categoryNameEn": "Cat2", "childrenList": []},
    ])

    def mock_query(category_ids, **kwargs):
        if category_ids == 2:
            time.sleep(0.05)
        return {"totalRow": 1, "totalPage": 1, "dataList": [{"productId": 900 + category_ids, "productCode": f"C{category_ids}"}]}

    api.query_products = MagicMock(side_effect=mock_query)

    scraper = LCSCScraper(api=api, db=db, max_duration=0.02, resume=True)

    count = scraper.run()
    assert scraper.time_limit_reached is True
    assert db.has_incomplete_progress()
    assert db.is_query_completed(1, 0, "")
    assert not db.is_query_completed(2, 0, "")

    db.close()



