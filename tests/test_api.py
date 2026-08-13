"""Unit and integration tests for LCSCApi."""

import pytest
from unittest.mock import MagicMock, patch

from lcsc_db.api import LCSCApi, LCSCApiConfig, LCSCApiError


def test_api_init_options():
    api = LCSCApi(LCSCApiConfig(delay_seconds=1.5, user_agent="CustomUserAgent/1.0", timeout=15.0))
    assert api.delay_seconds == 1.5
    assert api.session.headers["User-Agent"] == "CustomUserAgent/1.0"
    assert api.timeout == 15.0


def test_query_products_payload_options():
    api = LCSCApi(LCSCApiConfig(delay_seconds=0.0))
    
    with patch.object(api, "_request_with_retry") as mock_request:
        mock_request.return_value = {
            "result": {"dataList": [{"productId": 100, "productCode": "C100"}], "totalRow": 1}
        }

        # Test instock_only=True option
        api.query_products(category_ids=51, page=1, page_size=10, instock_only=True)
        mock_request.assert_called_with(
            "POST",
            "/product/query/list",
            json_payload={
                "currentPage": 1,
                "pageSize": 10,
                "catalogIdList": [51],
                "isStock": True,
            },
        )

        # Test instock_only=False option
        api.query_products(category_ids=51, page=2, page_size=50, instock_only=False)
        mock_request.assert_called_with(
            "POST",
            "/product/query/list",
            json_payload={
                "currentPage": 2,
                "pageSize": 50,
                "catalogIdList": [51],
            },
        )

        # Test keyword option
        api.query_products(category_ids=[10, 20], keyword="STM32", instock_only=False)
        mock_request.assert_called_with(
            "POST",
            "/product/query/list",
            json_payload={
                "currentPage": 1,
                "pageSize": 100,
                "catalogIdList": [10, 20],
                "keyword": "STM32",
            },
        )

        # Test brand_ids option
        api.query_products(category_ids=51, brand_ids=11615, instock_only=True)
        mock_request.assert_called_with(
            "POST",
            "/product/query/list",
            json_payload={
                "currentPage": 1,
                "pageSize": 100,
                "catalogIdList": [51],
                "brandIdList": [11615],
                "isStock": True,
            },
        )

        # Test get_param_group with brand_ids
        api.get_param_group(category_ids=1199, brand_ids=[11615, 815], instock_only=True)
        mock_request.assert_called_with(
            "POST",
            "/product/query/param/group",
            json_payload={
                "catalogIdList": [1199],
                "brandIdList": [11615, 815],
                "isStock": True,
            },
        )

        # Test get_catalog_list
        api.get_catalog_list(instock_only=True, brand_ids=[100], keyword="resistor")
        mock_request.assert_called_with(
            "POST",
            "/product/catalog/list",
            json_payload={
                "isStock": True,
                "isAsianBrand": False,
                "isEnvironment": False,
                "isOtherSuppliers": False,
                "isDeals": False,
                "brandIdList": [100],
                "searchText": "resistor",
            },
        )


@pytest.mark.integration
def test_live_get_category_tree():
    """Live API test for fetching category tree."""
    api = LCSCApi(LCSCApiConfig(delay_seconds=0.5))
    tree = api.get_category_tree()
    assert isinstance(tree, list)
    assert len(tree) > 0
    assert tree[0].category_id is not None
    assert tree[0].name_en


@pytest.mark.integration
def test_live_get_catalog_list():
    """Live API test for fetching catalog list."""
    api = LCSCApi(LCSCApiConfig(delay_seconds=0.5))
    cat_res = api.get_catalog_list(instock_only=True)
    assert isinstance(cat_res, object)
    assert cat_res.catalog_list
    assert cat_res.catalog_list[0].catalog_id is not None


@pytest.mark.integration
def test_live_query_products_options():
    """Live API test for querying products and param group with options."""
    api = LCSCApi(LCSCApiConfig(delay_seconds=0.5))

    # Test instock_only=True vs instock_only=False
    res_instock = api.query_products(category_ids=51, page=1, page_size=5, instock_only=True)
    res_all = api.query_products(category_ids=51, page=1, page_size=5, instock_only=False)

    assert isinstance(res_instock.data_list, list)
    assert isinstance(res_all.data_list, list)
    assert res_instock.total_row <= res_all.total_row

    # Test live get_param_group totalCount
    res_group = api.get_param_group(category_ids=51, instock_only=True)
    assert res_group.total_count > 0

