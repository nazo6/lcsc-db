"""LCSC API Client module."""

import logging
import time
from typing import Any, Dict, List, Optional, Union

import requests

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://wmsc.lcsc.com/ftps/wm"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class LCSCApiError(Exception):
    """Base exception for LCSC API errors."""

    pass


class LCSCApi:
    """Client for fetching category and product data from LCSC web APIs."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        user_agent: str = DEFAULT_USER_AGENT,
        delay_seconds: float = 2.0,
        max_retries: int = 5,
        backoff_factor: float = 2.0,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.delay_seconds = delay_seconds
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
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

    def get_category_tree(self) -> List[Dict[str, Any]]:
        """Fetch full category tree from /product/category/tree."""
        res = self._request_with_retry("GET", "/product/category/tree")
        if isinstance(res, dict) and "result" in res:
            return res["result"] or []
        return []

    def query_products(
        self,
        category_ids: Optional[Union[int, List[int]]] = None,
        page: int = 1,
        page_size: int = 100,
        instock_only: bool = True,
        keyword: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Query product list from /product/query/list.

        Args:
            category_ids: Single category ID or list of category IDs.
            page: Page number (1-indexed).
            page_size: Items per page (max 100).
            instock_only: If True, set isStock=True to filter in-stock items.
            keyword: Keyword search query string.

        Returns:
            Dict containing 'dataList', 'totalRow', 'currPage', 'totalPage'.
        """
        payload: Dict[str, Any] = {
            "currentPage": page,
            "pageSize": page_size,
        }

        if category_ids is not None:
            if isinstance(category_ids, list):
                payload["catalogIdList"] = category_ids
            else:
                payload["catalogIdList"] = [category_ids]

        if instock_only:
            payload["isStock"] = True

        if keyword:
            payload["keyword"] = keyword

        res = self._request_with_retry("POST", "/product/query/list", json_payload=payload)
        if isinstance(res, dict) and res.get("result"):
            return res["result"]
        return {"dataList": [], "totalRow": 0, "currPage": page, "totalPage": 0}
