"""CLI entrypoint for lcsc-db command."""

import argparse
import logging
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

from lcsc_db.api import LCSCApi, LCSCApiConfig
from lcsc_db.db import LCSCDatabase
from lcsc_db.jlcpcb import download_jlcpcb_cache
from lcsc_db.release import run_release_manager
from lcsc_db.scraper import LCSCScraper, ScraperConfig
from lcsc_db.variants import VARIANTS, compress_file, generate_all_variants


def compress_database(db_path: str) -> str:
    """Compress database file to .tar.xz archive using xz/tar if available, falling back to tarfile."""
    archive_path = compress_file(Path(db_path))
    return str(archive_path)


def run_create_variants(args: argparse.Namespace) -> None:
    """Execute database variant generation."""
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    selected = None if "all" in args.variants else args.variants
    generate_all_variants(
        base_db_path=Path(args.db_path),
        output_dir=Path(args.output_dir) if args.output_dir else None,
        selected_variants=selected,
        compress=args.compress,
    )


def run_update_release(args: argparse.Namespace) -> None:
    """Execute GitHub Release update and size stats logging."""
    run_release_manager(
        tag=args.tag,
        title=args.title,
        target_files=args.files,
        dry_run=args.dry_run,
    )


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
    jlc_parser.add_argument("--compress", action=argparse.BooleanOptionalAction, default=False, help="Compress database to .tar.xz archive upon completion.")
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
    scrape_parser.add_argument("--compress", action=argparse.BooleanOptionalAction, default=False, help="Compress database to .tar.xz archive upon completion.")
    scrape_parser.add_argument("--verbose", action=argparse.BooleanOptionalAction, default=False, help="Enable verbose DEBUG logging.")
    scrape_parser.set_defaults(func=run_scrape_lcsc)

    # Subcommand: create-variants
    variants_parser = subparsers.add_parser(
        "create-variants",
        help="Generate optimized database variants (e.g. fts_only, no_raw_json, minimal).",
    )
    variants_parser.add_argument("--db-path", default="lcsc.sqlite3", help="Input SQLite database file path.")
    variants_parser.add_argument("--output-dir", default=None, help="Output directory for generated variants.")
    variants_parser.add_argument(
        "--variants",
        nargs="+",
        choices=list(VARIANTS.keys()) + ["all"],
        default=["fts_only"],
        help="List of variants to generate (default: fts_only).",
    )
    variants_parser.add_argument("--compress", action=argparse.BooleanOptionalAction, default=True, help="Compress generated variants to .tar.xz archive.")
    variants_parser.add_argument("--verbose", action=argparse.BooleanOptionalAction, default=False, help="Enable verbose DEBUG logging.")
    variants_parser.set_defaults(func=run_create_variants)

    # Subcommand: update-release
    release_parser = subparsers.add_parser(
        "update-release",
        help="Upload files to GitHub Release and update release notes size table.",
    )
    release_parser.add_argument("--tag", default="latest", help="Release tag name (default: latest).")
    release_parser.add_argument(
        "--title",
        default="LCSC Product Database (Latest)",
        help="Release title (default: 'LCSC Product Database (Latest)').",
    )
    release_parser.add_argument(
        "--files",
        nargs="+",
        required=True,
        type=Path,
        help="List of files (.sqlite3 or .tar.xz) to inspect and upload.",
    )
    release_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print updated release notes without calling GitHub CLI.",
    )
    release_parser.set_defaults(func=run_update_release)

    # Default / Top-Level Arguments (Backwards Compatibility)
    parser.add_argument("--db-path", default="lcsc.sqlite3", help="Output SQLite database file path.")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay in seconds between API requests.")
    parser.add_argument("--instock-only", action=argparse.BooleanOptionalAction, default=True, help="Fetch only currently in-stock products.")
    parser.add_argument("--include-raw-json", action=argparse.BooleanOptionalAction, default=True, help="Save raw API JSON response.")
    parser.add_argument("--enable-fts", action=argparse.BooleanOptionalAction, default=True, help="Build SQLite FTS5 search index.")
    parser.add_argument("--category-id", type=int, default=None, help="Scrape only a specific category ID.")
    parser.add_argument("--max-pages", type=int, default=None, help="Maximum pages to scrape per category.")
    parser.add_argument("--compress", action=argparse.BooleanOptionalAction, default=False, help="Compress database to .tar.xz archive upon completion.")
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
