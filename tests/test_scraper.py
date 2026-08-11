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
