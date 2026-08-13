"""CLI entrypoint for lcsc-db command."""

import argparse
import logging
import os
import sys
import tarfile
from pathlib import Path

from lcsc_db.api import LCSCApi, LCSCApiConfig
from lcsc_db.db import LCSCDatabase
from lcsc_db.jlcpcb import download_jlcpcb_cache
from lcsc_db.scraper import LCSCScraper, ScraperConfig


def compress_database(db_path: str) -> str:
    """Compress database file to .tar.gz archive."""
    archive_path = f"{db_path}.tar.gz"
    print(f"Compressing {db_path} -> {archive_path}...")
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(db_path, arcname=os.path.basename(db_path))
    size_mb = os.path.getsize(archive_path) / (1024 * 1024)
    print(f"Compressed archive created: {archive_path} ({size_mb:.2f} MB)")
    return archive_path


def run_sync_jlcpcb(args: argparse.Namespace) -> None:
    """Execute JLCPCB cache download & database sync."""
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print("==================================================")
    print("JLCPCB Database Syncer -> LCSC Database")
    print(f"  Output DB Path  : {args.db_path}")
    print(f"  Cache Directory : {args.cache_dir}")
    print(f"  Build FTS5 Index: {args.enable_fts}")
    print("==================================================")

    cache_dir = Path(args.cache_dir)
    cache_path = download_jlcpcb_cache(target_dir=cache_dir)

    with LCSCDatabase(db_path=args.db_path) as db:
        db.init_schema(enable_fts=args.enable_fts)
        count = db.import_jlcpcb_cache(cache_path)
        if args.enable_fts:
            print("Rebuilding FTS5 trigram index...")
            db.rebuild_fts()
        db.vacuum_and_optimize()
        print(f"Successfully synced {count:,} JLCPCB products into {args.db_path}.")

    if args.compress:
        compress_database(args.db_path)


def run_scrape_lcsc(args: argparse.Namespace) -> None:
    """Execute LCSC API scraper."""
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print("==================================================")
    print("LCSC Product Database Scraper")
    print(f"  Output DB Path  : {args.db_path}")
    print(f"  Request Delay   : {args.delay}s")
    print(f"  In-Stock Only   : {args.instock_only}")
    print(f"  Include Raw JSON: {args.include_raw_json}")
    print(f"  Build FTS5 Index: {args.enable_fts}")
    if args.category_id:
        print(f"  Category Filter : #{args.category_id}")
    if args.max_pages:
        print(f"  Max Pages/Cat   : {args.max_pages}")
    print("==================================================")

    api = LCSCApi(LCSCApiConfig(delay_seconds=args.delay))
    with LCSCDatabase(db_path=args.db_path) as db:
        db.init_schema(enable_fts=args.enable_fts)
        config = ScraperConfig(
            db_path=args.db_path,
            delay=args.delay,
            instock_only=args.instock_only,
            include_raw_json=args.include_raw_json,
            enable_fts=args.enable_fts,
            category_id=args.category_id,
            max_pages=args.max_pages,
            compress=args.compress,
            verbose=args.verbose,
        )
        scraper = LCSCScraper(api=api, db=db, config=config)
        count = scraper.run(
            target_category_id=args.category_id,
            max_pages_per_category=args.max_pages,
        )

        expected_str = (
            f"{scraper.total_expected_products:,}"
            if scraper.total_expected_products > 0
            else "N/A"
        )
        print(
            f"Successfully processed {count:,} unique products in {args.db_path} "
            f"(Expected: {expected_str} products, Fetched: {scraper.total_fetched_items:,} items)."
        )

    if args.compress:
        compress_database(args.db_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lcsc-db",
        description="Scraper and SQLite database builder for LCSC and JLCPCB electronics components.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # Subcommand: sync-jlcpcb
    jlc_parser = subparsers.add_parser(
        "sync-jlcpcb",
        help="Download JLCPCB cache database and sync ~7.12M components into lcsc.sqlite3.",
    )
    jlc_parser.add_argument("--db-path", default="lcsc.sqlite3", help="Output SQLite database file path.")
    jlc_parser.add_argument("--cache-dir", default=".jlcpcb_cache", help="Temporary directory to download JLCPCB cache chunks.")
    jlc_parser.add_argument("--enable-fts", action=argparse.BooleanOptionalAction, default=True, help="Build SQLite FTS5 trigram search index.")
    jlc_parser.add_argument("--compress", action=argparse.BooleanOptionalAction, default=False, help="Compress database to .tar.gz archive upon completion.")
    jlc_parser.add_argument("--verbose", action=argparse.BooleanOptionalAction, default=False, help="Enable verbose DEBUG logging.")
    jlc_parser.set_defaults(func=run_sync_jlcpcb)

    # Subcommand: scrape-lcsc
    scrape_parser = subparsers.add_parser(
        "scrape-lcsc",
        help="Scrape real-time stock and prices from LCSC API.",
    )
    scrape_parser.add_argument("--db-path", default="lcsc.sqlite3", help="Output SQLite database file path.")
    scrape_parser.add_argument("--delay", type=float, default=2.0, help="Delay in seconds between API requests.")
    scrape_parser.add_argument("--instock-only", action=argparse.BooleanOptionalAction, default=True, help="Fetch only currently in-stock products.")
    scrape_parser.add_argument("--include-raw-json", action=argparse.BooleanOptionalAction, default=True, help="Save raw API JSON response.")
    scrape_parser.add_argument("--enable-fts", action=argparse.BooleanOptionalAction, default=True, help="Build SQLite FTS5 search index.")
    scrape_parser.add_argument("--category-id", type=int, default=None, help="Scrape only a specific category ID.")
    scrape_parser.add_argument("--max-pages", type=int, default=None, help="Maximum pages to scrape per category.")
    scrape_parser.add_argument("--compress", action=argparse.BooleanOptionalAction, default=False, help="Compress database to .tar.gz archive upon completion.")
    scrape_parser.add_argument("--verbose", action=argparse.BooleanOptionalAction, default=False, help="Enable verbose DEBUG logging.")
    scrape_parser.set_defaults(func=run_scrape_lcsc)

    # Default / Top-Level Arguments (Backwards Compatibility)
    parser.add_argument("--db-path", default="lcsc.sqlite3", help="Output SQLite database file path.")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay in seconds between API requests.")
    parser.add_argument("--instock-only", action=argparse.BooleanOptionalAction, default=True, help="Fetch only currently in-stock products.")
    parser.add_argument("--include-raw-json", action=argparse.BooleanOptionalAction, default=True, help="Save raw API JSON response.")
    parser.add_argument("--enable-fts", action=argparse.BooleanOptionalAction, default=True, help="Build SQLite FTS5 search index.")
    parser.add_argument("--category-id", type=int, default=None, help="Scrape only a specific category ID.")
    parser.add_argument("--max-pages", type=int, default=None, help="Maximum pages to scrape per category.")
    parser.add_argument("--compress", action=argparse.BooleanOptionalAction, default=False, help="Compress database to .tar.gz archive upon completion.")
    parser.add_argument("--verbose", action=argparse.BooleanOptionalAction, default=False, help="Enable verbose DEBUG logging.")
    parser.set_defaults(func=run_scrape_lcsc)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        run_scrape_lcsc(args)


if __name__ == "__main__":
    main()
