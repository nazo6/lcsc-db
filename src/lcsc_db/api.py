"""LCSC API Client module."""

import logging
import time
from typing import Any, Dict, Optional, Union

import requests
from pydantic import BaseModel

from lcsc_db.models import (
    CatalogListResult,
    Category,
    ParamGroupResult,
    ProductQueryResult,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://wmsc.lcsc.com/ftps/wm"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class LCSCApiConfig(BaseModel):
    """Configuration for the LCSC API client."""

    base_url: str = DEFAULT_BASE_URL
    user_agent: str = DEFAULT_USER_AGENT
    delay_seconds: float = 2.0
    max_retries: int = 5
    backoff_factor: float = 2.0
    timeout: float = 30.0


class LCSCApiError(Exception):
    """Base exception for LCSC API errors."""

    pass


class LCSCApi:
    """Client for fetching category and product data from LCSC web APIs."""

    def __init__(self, config: Optional[LCSCApiConfig] = None) -> None:
        config = config or LCSCApiConfig()
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        self.delay_seconds = config.delay_seconds
        self.max_retries = config.max_retries
        self.backoff_factor = config.backoff_factor
        self.timeout = config.timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": config.user_agent,
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
            }
        )

    def _request_with_retry(
        self, method: str, endpoint: str, json_payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        retries = 0
        current_delay = self.delay_seconds

        while True:
            if self.delay_seconds > 0:
                time.sleep(self.delay_seconds)

            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    json=json_payload,
                    timeout=self.timeout,
                )

                if response.status_code == 200:
                    data = response.json()
                    if not data.get("ok") and data.get("code") not in (200, None):
                        msg = data.get("msg") or f"API error code {data.get('code')}"
                        logger.warning("LCSC API reported error: %s", msg)
                        # Rate limit code 405 or general search error
                        if data.get("code") in (405, 429):
                            raise LCSCApiError(f"Rate limited or forbidden: {msg}")
                    return data

                if response.status_code in (429, 403, 502, 503, 504):
                    logger.warning(
                        "HTTP %d from LCSC API. Retry %d/%d after %.1fs backoff...",
                        response.status_code,
                        retries + 1,
                        self.max_retries,
                        current_delay * 10,
                    )
                    time.sleep(current_delay * 10)
                else:
                    response.raise_for_status()

            except (requests.RequestException, LCSCApiError, ValueError) as exc:
                retries += 1
                if retries > self.max_retries:
                    raise LCSCApiError(
                        f"Failed request to {url} after {self.max_retries} retries: {exc}"
                    ) from exc
                time.sleep(current_delay)
                current_delay *= self.backoff_factor

    def get_category_tree(self) -> list[Category]:
        """Fetch full category tree from /product/category/tree."""
        res = self._request_with_retry("GET", "/product/category/tree")
        raw = res.get("result") or [] if isinstance(res, dict) else []
        return [Category.model_validate(item) for item in raw]

    @staticmethod
    def _as_list(value: Optional[Union[int, list[int]]]) -> Optional[list[int]]:
        """Normalize a single ID or list of IDs into a list (or None)."""
        if value is None:
            return None
        return [value] if isinstance(value, int) else list(value)

    def query_products(
        self,
        category_ids: Optional[Union[int, list[int]]] = None,
        brand_ids: Optional[Union[int, list[int]]] = None,
        page: int = 1,
        page_size: int = 100,
        instock_only: bool = True,
        keyword: Optional[str] = None,
    ) -> ProductQueryResult:
        """Query product list from /product/query/list.

        Args:
            category_ids: Single category ID or list of category IDs.
            brand_ids: Single brand/manufacturer ID or list of brand IDs.
            page: Page number (1-indexed).
            page_size: Items per page (max 100).
            instock_only: If True, set isStock=True to filter in-stock items.
            keyword: Keyword search query string.

        Returns:
            ProductQueryResult containing dataList, totalRow, currPage, totalPage.
        """
        payload: Dict[str, Any] = {
            "currentPage": page,
            "pageSize": page_size,
        }

        if (cl := self._as_list(category_ids)) is not None:
            payload["catalogIdList"] = cl

        if (bl := self._as_list(brand_ids)) is not None:
            payload["brandIdList"] = bl

        if instock_only:
            payload["isStock"] = True

        if keyword:
            payload["keyword"] = keyword

        res = self._request_with_retry("POST", "/product/query/list", json_payload=payload)
        return ProductQueryResult.model_validate(res.get("result") or {} if isinstance(res, dict) else {})

    def get_param_group(
        self,
        category_ids: Optional[Union[int, list[int]]] = None,
        brand_ids: Optional[Union[int, list[int]]] = None,
        instock_only: bool = True,
        keyword: Optional[str] = None,
    ) -> ParamGroupResult:
        """Fetch parameter groups and accurate totalCount from /product/query/param/group.

        Args:
            category_ids: Single category ID or list of category IDs.
            brand_ids: Single brand/manufacturer ID or list of brand IDs.
            instock_only: If True, filter in-stock items.
            keyword: Keyword search query string.

        Returns:
            ParamGroupResult containing totalCount and parameter group attributes.
        """
        payload: Dict[str, Any] = {}

        if (cl := self._as_list(category_ids)) is not None:
            payload["catalogIdList"] = cl

        if (bl := self._as_list(brand_ids)) is not None:
            payload["brandIdList"] = bl

        if instock_only:
            payload["isStock"] = True

        if keyword:
            payload["keyword"] = keyword

        res = self._request_with_retry("POST", "/product/query/param/group", json_payload=payload)
        return ParamGroupResult.model_validate(res.get("result") or {} if isinstance(res, dict) else {})

    def get_catalog_list(
        self,
        instock_only: bool = True,
        brand_ids: Optional[Union[int, list[int]]] = None,
        keyword: Optional[str] = None,
    ) -> CatalogListResult:
        """Fetch catalog list and pre-calculated product counts from /product/catalog/list.

        Args:
            instock_only: If True, set isStock=True.
            brand_ids: Single brand ID or list of brand IDs.
            keyword: Search keyword text.

        Returns:
            CatalogListResult containing catalogList and brandList.
        """
        payload: Dict[str, Any] = {
            "isStock": instock_only,
            "isAsianBrand": False,
            "isEnvironment": False,
            "isOtherSuppliers": False,
            "isDeals": False,
            "searchText": keyword or "",
            "brandIdList": self._as_list(brand_ids) or [],
        }

        res = self._request_with_retry("POST", "/product/catalog/list", json_payload=payload)
        return CatalogListResult.model_validate(res.get("result") or {} if isinstance(res, dict) else {})

