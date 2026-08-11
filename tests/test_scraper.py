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


def test_scraper_partitioning_trigger(tmp_path):
    """Test that totalRow >= 5000 triggers prefix sub-partitioning."""
    db_file = tmp_path / "test_partition.sqlite3"
    api = LCSCApi(delay_seconds=0.0)
    db = LCSCDatabase(str(db_file))

    scraper = LCSCScraper(
        api=api,
        db=db,
        instock_only=True,
        partition_threshold=100,  # Lower threshold for testing
        max_partition_depth=1,
    )

    mock_query_response_500 = {
        "totalRow": 500,  # Exceeds threshold 100
        "totalPage": 5,
        "dataList": [{"productId": 999, "productCode": "C999", "productModel": "M999"}],
    }

    mock_query_response_50 = {
        "totalRow": 50,
        "totalPage": 1,
        "dataList": [{"productId": 1001, "productCode": "C1001", "productModel": "M1001"}],
    }

    def mock_query(category_ids, page=1, page_size=100, instock_only=True, keyword=None):
        if keyword is None:
            return mock_query_response_500
        return mock_query_response_50

    api.query_products = MagicMock(side_effect=mock_query)

    # Run query for cat 100
    db.init_schema()
    count = scraper._scrape_category_query(cat_id=100, cat_path="Test Cat", depth=0)

    # Should have called partitioned sub-queries for 0..9, a..z
    assert api.query_products.call_count > 1
    assert count > 0

    db.close()
