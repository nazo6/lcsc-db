"""Scraper module orchestrating LCSC category tree traversal and product scraping."""

import logging
import signal
import string
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from tqdm import tqdm

from lcsc_db.api import LCSCApi
from lcsc_db.db import LCSCDatabase

logger = logging.getLogger(__name__)

# Alphanumeric characters used for prefix sub-partitioning
PARTITION_CHARS = string.digits + string.ascii_lowercase


class LCSCScraper:
    """Orchestrator for scraping LCSC category tree and product details into SQLite."""

    def __init__(
        self,
        api: LCSCApi,
        db: LCSCDatabase,
        instock_only: bool = True,
        include_raw_json: bool = True,
        enable_fts: bool = True,
        partition_threshold: int = 5000,
        max_partition_depth: int = 2,
        max_duration: Optional[float] = None,
        resume: bool = True,
        fresh: bool = False,
    ) -> None:
        self.api = api
        self.db = db
        self.instock_only = instock_only
        self.include_raw_json = include_raw_json
        self.enable_fts = enable_fts
        self.partition_threshold = partition_threshold
        self.max_partition_depth = max_partition_depth
        self.max_duration = max_duration
        self.resume = resume
        self.fresh = fresh

        self.seen_product_ids: Set[int] = set()
        self.start_time: float = 0.0
        self.interrupted: bool = False
        self.time_limit_reached: bool = False

    def _should_stop(self) -> bool:
        """Check if scraping should be stopped due to signal or max duration time limit."""
        if self.interrupted:
            return True
        if self.max_duration and self.start_time > 0:
            elapsed = time.time() - self.start_time
            if elapsed >= self.max_duration:
                if not self.time_limit_reached:
                    logger.warning(
                        "Execution max duration limit reached (%.1fs >= %.1fs). Stopping gracefully...",
                        elapsed,
                        self.max_duration,
                    )
                    self.time_limit_reached = True
                return True
        return False

    def _extract_all_categories(
        self, cat_list: List[Dict[str, Any]], flat_list: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """Flatten category tree to list of category objects."""
        if flat_list is None:
            flat_list = []
        for cat in cat_list:
            flat_list.append(cat)
            children = cat.get("childrenList") or []
            if children:
                self._extract_all_categories(children, flat_list)
        return flat_list

    def _find_leaf_categories(
        self, cat_list: List[Dict[str, Any]], path: str = ""
    ) -> List[Tuple[int, str]]:
        """Find all leaf category IDs and their breadcrumb names."""
        leaf_cats: List[Tuple[int, str]] = []
        for c in cat_list:
            cid = c.get("categoryId")
            name = c.get("categoryNameEn") or c.get("categoryNameCn") or str(cid)
            cur_path = f"{path} > {name}" if path else name
            children = c.get("childrenList") or []
            if not children:
                if cid:
                    leaf_cats.append((cid, cur_path))
            else:
                leaf_cats.extend(self._find_leaf_categories(children, cur_path))
        return leaf_cats

    def _scrape_category_query(
        self,
        cat_id: int,
        cat_path: str,
        brand_id: Optional[int] = None,
        brand_name: Optional[str] = None,
        keyword: Optional[str] = None,
        max_pages_per_category: Optional[int] = None,
        pbar: Optional[tqdm] = None,
    ) -> int:
        """Scrape products for a category, optionally partitioned by brand and/or keyword."""
        if self._should_stop():
            return 0

        if self.resume and self.db.is_query_completed(cat_id, brand_id, keyword):
            logger.debug(
                "Skipping already completed query: cat=%d, brand=%s, kw=%s",
                cat_id,
                brand_id,
                keyword,
            )
            return 0

        # Test first page to get totalRow count
        res_first = self.api.query_products(
            category_ids=cat_id,
            brand_ids=brand_id,
            page=1,
            page_size=100,
            instock_only=self.instock_only,
            keyword=keyword,
        )

        total_rows = res_first.get("totalRow") or 0

        # Optimization: Immediately skip empty categories/queries
        if total_rows == 0:
            if pbar:
                b_str = f" [brand='{brand_name or brand_id}']" if brand_id else ""
                kw_str = f" [kw='{keyword}']" if keyword else ""
                pbar.set_postfix_str(f"{cat_path}{b_str}{kw_str} (0 items)")
            self.db.mark_query_completed(cat_id, brand_id, keyword, total_rows=0, scraped_count=0)
            return 0

        # Check if sub-partitioning is required
        if total_rows >= self.partition_threshold:
            # Step 1: Primary partition by Manufacturer / Brand if brand_id is not set
            if brand_id is None:
                param_group = self.api.get_param_group(
                    category_ids=cat_id,
                    instock_only=self.instock_only,
                    keyword=keyword,
                )
                mfrs = param_group.get("Manufacturer") or []
                if mfrs:
                    logger.info(
                        "Category %s (totalRow=%d >= %d) partitioning by %d manufacturers...",
                        cat_path,
                        total_rows,
                        self.partition_threshold,
                        len(mfrs),
                    )
                    count = 0
                    for m in mfrs:
                        if self._should_stop():
                            break
                        m_id = int(m["id"])
                        m_name = m.get("name") or str(m_id)
                        count += self._scrape_category_query(
                            cat_id=cat_id,
                            cat_path=cat_path,
                            brand_id=m_id,
                            brand_name=m_name,
                            keyword=keyword,
                            max_pages_per_category=max_pages_per_category,
                            pbar=pbar,
                        )
                    return count

            # Step 2: Secondary fallback to single-char keyword (0-9a-z) if keyword is not set
            if keyword is None:
                b_info = f"brand '{brand_name}' ({brand_id})" if brand_id else "no brand"
                logger.info(
                    "Category %s [%s] (totalRow=%d >= %d) falling back to 0-z keyword split...",
                    cat_path,
                    b_info,
                    total_rows,
                    self.partition_threshold,
                )
                count = 0
                for char in PARTITION_CHARS:
                    if self._should_stop():
                        break
                    count += self._scrape_category_query(
                        cat_id=cat_id,
                        cat_path=cat_path,
                        brand_id=brand_id,
                        brand_name=brand_name,
                        keyword=char,
                        max_pages_per_category=max_pages_per_category,
                        pbar=pbar,
                    )
                return count

            # Step 3: If brand_id and keyword are both set and still >= partition_threshold
            b_info = f"brand '{brand_name}' ({brand_id})" if brand_id else "no brand"
            logger.warning(
                "Category %s [%s, kw='%s'] totalRow=%d >= %d. Exceeds max pagination capacity even after brand+keyword split; scraping available pages without further splitting.",
                cat_path,
                b_info,
                keyword,
                total_rows,
                self.partition_threshold,
            )

        # Standard page loop for this query
        page = 1
        query_scraped_count = 0

        while True:
            if self._should_stop():
                break

            if page == 1:
                res = res_first
            else:
                res = self.api.query_products(
                    category_ids=cat_id,
                    brand_ids=brand_id,
                    page=page,
                    page_size=100,
                    instock_only=self.instock_only,
                    keyword=keyword,
                )

            items = res.get("dataList") or []
            total_pages = res.get("totalPage") or 0
            t_rows = res.get("totalRow") or 0

            if pbar:
                page_info = f"p.{page}/{total_pages}" if total_pages > 1 else f"p.{page}"
                b_str = f" [brand='{brand_name or brand_id}']" if brand_id else ""
                kw_str = f" [kw='{keyword}']" if keyword else ""
                pbar.set_postfix_str(f"{cat_path}{b_str}{kw_str} ({t_rows} items, {page_info})")

            if not items:
                break

            self.db.upsert_products(items, include_raw_json=self.include_raw_json)

            pids: Set[int] = set()
            for item in items:
                pid = item.get("productId")
                if pid:
                    pids.add(pid)
                    self.seen_product_ids.add(pid)
                    query_scraped_count += 1

            self.db.record_seen_products(pids)

            if page >= total_pages:
                break

            if max_pages_per_category and page >= max_pages_per_category:
                break

            page += 1

        if not self._should_stop():
            self.db.mark_query_completed(
                cat_id, brand_id, keyword, total_rows=total_rows, scraped_count=query_scraped_count
            )

        return query_scraped_count

    def run(
        self,
        target_category_id: Optional[int] = None,
        max_pages_per_category: Optional[int] = None,
    ) -> int:
        """Run the scraping process across all leaf categories.

        Args:
            target_category_id: Optional single category ID to scrape.
            max_pages_per_category: Optional limit on pages scraped per category.

        Returns:
            Total count of unique products processed.
        """
        def _signal_handler(signum: int, frame: Any) -> None:
            logger.warning("Received signal %d. Shutdown requested...", signum)
            self.interrupted = True

        try:
            signal.signal(signal.SIGINT, _signal_handler)
            signal.signal(signal.SIGTERM, _signal_handler)
        except (ValueError, AttributeError):
            pass

        self.start_time = time.time()

        logger.info("Initializing database schema...")
        self.db.init_schema(
            include_raw_json=self.include_raw_json, enable_fts=self.enable_fts
        )

        if self.fresh:
            logger.info("Fresh flag set. Clearing previous scrape progress...")
            self.db.clear_scrape_progress()

        logger.info("Fetching category tree from LCSC API...")
        cat_tree = self.api.get_category_tree()

        if cat_tree:
            all_cats = self._extract_all_categories(cat_tree)
            self.db.upsert_categories(all_cats)
            logger.info("Saved %d categories to database.", len(all_cats))

        if target_category_id:
            leaf_cats = [(target_category_id, f"Category #{target_category_id}")]
        else:
            leaf_cats = self._find_leaf_categories(cat_tree)

        logger.info("Starting scrape across %d categories...", len(leaf_cats))

        pbar = tqdm(leaf_cats, desc="Categories", unit="cat")
        for cat_id, cat_path in pbar:
            if self._should_stop():
                logger.info("Stopping category processing loop due to signal or duration limit.")
                break
            self._scrape_category_query(
                cat_id=cat_id,
                cat_path=cat_path,
                max_pages_per_category=max_pages_per_category,
                pbar=pbar,
            )

        if self._should_stop():
            logger.warning(
                "Scraping suspended before completion (%d products processed so far). Progress saved for resume.",
                len(self.seen_product_ids),
            )
            return len(self.seen_product_ids)

        logger.info("Completed all categories. Scraped %d unique products in this run.", len(self.seen_product_ids))

        if self.instock_only and target_category_id is None:
            logger.info("Updating stock for unseen products to 0...")
            self.db.mark_unseen_stock_zero_from_db()

        if self.enable_fts:
            logger.info("Rebuilding FTS5 full-text search index...")
            self.db.rebuild_fts()

        logger.info("Optimizing database...")
        self.db.vacuum_and_optimize()

        logger.info("Clearing completed scrape progress tracking tables...")
        self.db.clear_scrape_progress()

        return len(self.seen_product_ids)

