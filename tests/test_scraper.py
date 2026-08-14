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


def test_format_duration():
    from lcsc_db.progress import format_duration

    assert format_duration(5) == "5s"
    assert format_duration(65) == "1m 05s"
    assert format_duration(3665) == "1h 01m 05s"


def test_scraper_item_tracking_and_catalog_list_expected(tmp_path):
    """Test that total_expected_products and total_fetched_items are accurately tracked."""
    db_file = tmp_path / "test_item_tracking.sqlite3"
    api = LCSCApi(LCSCApiConfig(delay_seconds=0.0))
    db = LCSCDatabase(str(db_file))

    scraper = LCSCScraper(api=api, db=db)

    api.get_category_tree = MagicMock(return_value=[])
    api.get_catalog_list = MagicMock(
        return_value=CatalogListResult.model_validate({
            "catalogList": [
                {
                    "catalogId": 1,
                    "catalogNameEn": "Resistors",
                    "productNum": 150,
                    "childCatelogs": [],
                },
                {
                    "catalogId": 2,
                    "catalogNameEn": "Capacitors",
                    "productNum": 250,
                    "childCatelogs": [],
                },
            ]
        })
    )

    api.query_products = MagicMock(
        return_value=ProductQueryResult(
            total_row=10,
            total_page=1,
            data_list=[
                Product(product_id=1, lcsc_number="C1"),
                Product(product_id=2, lcsc_number="C2"),
            ],
        )
    )

    count = scraper.run()
    assert scraper.total_expected_products == 400
    assert scraper.total_fetched_items == 4  # 2 products fetched per category (2 categories)
    assert count == 2  # Deduplicated unique product IDs: {1, 2}

    db.close()


def test_scraper_tree_leaf_resolution_overrides_truncated_catalog_list(tmp_path):
    """Test that true leaf categories from category_tree are queried even if catalog_list truncates parent nodes."""
    db_file = tmp_path / "test_tree_leaf_resolution.sqlite3"
    api = LCSCApi(LCSCApiConfig(delay_seconds=0.0))
    db = LCSCDatabase(str(db_file))

    scraper = LCSCScraper(api=api, db=db)

    # Cat 1433 in category_tree has children 1434 and 1435
    api.get_category_tree = MagicMock(
        return_value=[
            Category(
                category_id=1433,
                name_en="FETs, MOSFETs",
                children=[
                    Category(category_id=1434, name_en="FET Arrays", children=[]),
                    Category(category_id=1435, name_en="Single FETs", children=[]),
                ],
            )
        ]
    )

    # catalog_list lists 1433 as leaf entry with 40,000 productNum
    api.get_catalog_list = MagicMock(
        return_value=CatalogListResult.model_validate({
            "catalogList": [
                {
                    "catalogId": 1433,
                    "catalogNameEn": "FETs, MOSFETs",
                    "productNum": 40000,
                    "childCatelogs": [],
                }
            ]
        })
    )

    queried_cat_ids = []

    def mock_query(category_ids, brand_ids=None, page=1, page_size=100, instock_only=True, keyword=None):
        cid = category_ids[0] if isinstance(category_ids, list) else category_ids
        queried_cat_ids.append(cid)
        return ProductQueryResult(
            total_row=10,
            total_page=1,
            data_list=[Product(product_id=cid, lcsc_number=f"C{cid}")],
        )

    api.query_products = MagicMock(side_effect=mock_query)

    count = scraper.run()

    # Should query subcategories 1434 and 1435, NOT parent 1433
    assert 1433 not in queried_cat_ids
    assert 1434 in queried_cat_ids
    assert 1435 in queried_cat_ids
    assert count == 2

    db.close()



