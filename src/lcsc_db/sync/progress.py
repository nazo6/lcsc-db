"""Progress logging utilities for LCSC product scraper."""

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


def format_duration(seconds: float) -> str:
    """Format duration in seconds into human-readable string (e.g. 1h 23m 45s, 12m 34s, 5s)."""
    secs = int(max(0, seconds))
    hours, remainder = divmod(secs, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    elif minutes > 0:
        return f"{minutes}m {secs:02d}s"
    else:
        return f"{secs}s"


class ScrapeProgressLogger:
    """Manages progress tracking, speed calculation, ETA, and logging during scraping runs."""

    def __init__(self, total_expected_products: int = 0, total_cats: int = 0) -> None:
        self.total_expected_products: int = total_expected_products
        self.total_cats: int = total_cats
        self.total_fetched_items: int = 0
        self.start_time: float = time.time()

    def start(self) -> None:
        """Log scrape initialization."""
        self.start_time = time.time()
        self.total_fetched_items = 0
        if self.total_expected_products > 0:
            logger.info(
                "Starting scrape across %d categories. Total expected products: %s",
                self.total_cats,
                f"{self.total_expected_products:,}",
            )
        else:
            logger.info("Starting scrape across %d categories...", self.total_cats)

    def log_page(
        self,
        cat_idx: int,
        total_cats: int,
        cat_path: str,
        page: int,
        total_pages: int,
        t_rows: int,
        items_count: int,
        brand_name: Optional[str] = None,
        brand_id: Optional[int] = None,
        keyword: Optional[str] = None,
    ) -> None:
        """Format and log page progress line with ETA and items/s rate."""
        self.total_fetched_items += items_count

        b_str = f" [brand='{brand_name or brand_id}']" if brand_id else ""
        kw_str = f" [kw='{keyword}']" if keyword else ""
        page_info = f"p.{page}/{total_pages}" if total_pages > 1 else f"p.{page}"

        elapsed = time.time() - self.start_time if self.start_time else 0.0
        rate = (self.total_fetched_items / elapsed) if elapsed > 0 else 0.0

        if self.total_expected_products > 0:
            pct = (self.total_fetched_items / self.total_expected_products) * 100.0
            pct_str = f"{pct:.1f}%"
            remaining = max(0, self.total_expected_products - self.total_fetched_items)
            eta_seconds = (remaining / rate) if rate > 0 else 0.0
            eta_str = format_duration(eta_seconds) if rate > 0 else "N/A"
            total_str = f"{self.total_fetched_items:,}/{self.total_expected_products:,} items ({pct_str})"
            stats_str = f" | {rate:.1f} items/s, ETA: {eta_str}"
        else:
            total_str = f"{self.total_fetched_items:,} items"
            stats_str = f" | {rate:.1f} items/s"

        logger.info(
            "[Cat %d/%d] %s%s%s %s (%d items) | Total: %s%s",
            cat_idx,
            total_cats,
            cat_path,
            b_str,
            kw_str,
            page_info,
            t_rows,
            total_str,
            stats_str,
        )

    def log_empty(
        self,
        cat_idx: int,
        total_cats: int,
        cat_path: str,
        brand_name: Optional[str] = None,
        brand_id: Optional[int] = None,
        keyword: Optional[str] = None,
    ) -> None:
        """Format and log skipped empty category line."""
        b_str = f" [brand='{brand_name or brand_id}']" if brand_id else ""
        kw_str = f" [kw='{keyword}']" if keyword else ""

        elapsed = time.time() - self.start_time if self.start_time else 0.0
        rate = (self.total_fetched_items / elapsed) if elapsed > 0 else 0.0

        if self.total_expected_products > 0:
            pct = (self.total_fetched_items / self.total_expected_products) * 100.0
            pct_str = f"{pct:.1f}%"
            remaining = max(0, self.total_expected_products - self.total_fetched_items)
            eta_seconds = (remaining / rate) if rate > 0 else 0.0
            eta_str = format_duration(eta_seconds) if rate > 0 else "N/A"
            total_str = f"{self.total_fetched_items:,}/{self.total_expected_products:,} items ({pct_str})"
            stats_str = f" | {rate:.1f} items/s, ETA: {eta_str}"
        else:
            total_str = f"{self.total_fetched_items:,} items"
            stats_str = f" | {rate:.1f} items/s"

        logger.info(
            "[Cat %d/%d] %s%s%s (0 items) | Total: %s%s",
            cat_idx,
            total_cats,
            cat_path,
            b_str,
            kw_str,
            total_str,
            stats_str,
        )

    def complete(self, unique_product_count: int) -> None:
        """Log scrape completion summary."""
        elapsed_total = time.time() - self.start_time
        duration_str = format_duration(elapsed_total)
        pct_str = (
            f"{(self.total_fetched_items / self.total_expected_products * 100):.1f}%"
            if self.total_expected_products > 0
            else "N/A"
        )

        logger.info(
            "Completed all categories in %s. Expected: %s products | Fetched: %s items (%s) | Saved %s unique products in this run.",
            duration_str,
            f"{self.total_expected_products:,}" if self.total_expected_products > 0 else "N/A",
            f"{self.total_fetched_items:,}",
            pct_str,
            f"{unique_product_count:,}",
        )
