"""Integration and unit tests for LCSCScraper."""

import pytest
from unittest.mock import MagicMock

from sqlmodel import Session, func, select

from lcsc_db.api import LCSCApi, LCSCApiConfig
from lcsc_db.db import LCSCDatabase
from lcsc_db.models import (
    CatalogListResult,
    Category,
    ParamGroupResult,
    Product,
    ProductQueryResult,
)
from lcsc_db.schema import ProductRecord
from lcsc_db.scraper import LCSCScraper, ScraperConfig


def test_scraper_options_and_run(tmp_path):
    db_file = tmp_path / "test_scraper.sqlite3"
    api = LCSCApi(LCSCApiConfig(delay_seconds=0.0))
    db = LCSCDatabase(str(db_file))

    scraper = LCSCScraper(
        api=api,
        db=db,
        config=ScraperConfig(
            instock_only=True,
            include_raw_json=True,
            enable_fts=True,
        ),
    )

    # Scrape category 51 with max 1 page
    count = scraper.run(target_category_id=51, max_pages_per_category=1)
    assert count >= 0

    with Session(db.engine) as session:
        total_in_db = session.exec(select(func.count()).select_from(ProductRecord)).one()
    assert total_in_db == count

    db.close()


def test_scraper_brand_partitioning_trigger(tmp_path):
    """Test that totalRow >= threshold triggers brand-based partitioning."""
    db_file = tmp_path / "test_brand_partition.sqlite3"
    api = LCSCApi(LCSCApiConfig(delay_seconds=0.0))
    db = LCSCDatabase(str(db_file))

    scraper = LCSCScraper(
        api=api,
        db=db,
        config=ScraperConfig(
            instock_only=True,
            partition_threshold=100,  # Lower threshold for testing
        ),
    )

    api.get_param_group = MagicMock(return_value=ParamGroupResult.model_validate({
        "Manufacturer": [
            {"id": "1001", "name": "BrandA"},
            {"id": "1002", "name": "BrandB"},
        ]
    }))

    def mock_query(category_ids, brand_ids=None, page=1, page_size=100, instock_only=True, keyword=None):
        if brand_ids is None:
            return ProductQueryResult(
                total_row=500,
                total_page=5,
                data_list=[Product(product_id=1, lcsc_number="C1")],
            )
        bid = brand_ids[0] if isinstance(brand_ids, list) else brand_ids
        return ProductQueryResult(
            total_row=50,
            total_page=1,
            data_list=[Product(product_id=int(bid), lcsc_number=f"C{bid}")],
        )

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
    api = LCSCApi(LCSCApiConfig(delay_seconds=0.0))
    db = LCSCDatabase(str(db_file))

    scraper = LCSCScraper(
        api=api,
        db=db,
        config=ScraperConfig(
            instock_only=True,
            partition_threshold=100,
        ),
    )

    # Return no manufacturers to test direct fallback to keyword
    api.get_param_group = MagicMock(return_value=ParamGroupResult.model_validate({"Manufacturer": []}))

    def mock_query(category_ids, brand_ids=None, page=1, page_size=100, instock_only=True, keyword=None):
        # Always returns totalRow 200 >= threshold 100
        return ProductQueryResult(
            total_row=200,
            total_page=2,
            data_list=[Product(product_id=99, lcsc_number="C99")],
        )

    api.query_products = MagicMock(side_effect=mock_query)

    db.init_schema()
    import logging
    with caplog.at_level(logging.WARNING):
        count = scraper._scrape_category_query(cat_id=100, cat_path="Test Cat", brand_id=55, brand_name="BrandX")

    # Should have triggered 0-z keyword split (36 chars) and logged warnings for each char without infinite recursion
    assert "Exceeds max pagination capacity even after brand+keyword split" in caplog.text
    assert count > 0

    db.close()

