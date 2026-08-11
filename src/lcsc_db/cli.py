"""CLI entrypoint for lcsc-db command."""

import logging
import os
import tarfile
import sys
from typing import Optional

import click

from lcsc_db.api import LCSCApi
from lcsc_db.db import LCSCDatabase
from lcsc_db.scraper import LCSCScraper


def compress_database(db_path: str) -> str:
    """Compress database file to .tar.gz archive."""
    archive_path = f"{db_path}.tar.gz"
    click.echo(f"Compressing {db_path} -> {archive_path}...")
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(db_path, arcname=os.path.basename(db_path))
    size_mb = os.path.getsize(archive_path) / (1024 * 1024)
    click.echo(f"Compressed archive created: {archive_path} ({size_mb:.2f} MB)")
    return archive_path


@click.command(help="LCSC Product Catalog Database Builder CLI")
@click.option(
    "--db-path",
    default="lcsc.sqlite3",
    show_default=True,
    help="Path to output SQLite database file.",
)
@click.option(
    "--delay",
    default=2.0,
    show_default=True,
    type=float,
    help="Delay in seconds between API requests.",
)
@click.option(
    "--instock-only/--all-parts",
    default=True,
    show_default=True,
    help="Fetch only currently in-stock products to save ~70% API calls vs fetch all parts.",
)
@click.option(
    "--include-raw-json/--no-raw-json",
    default=True,
    show_default=True,
    help="Save raw API JSON response in raw_json column for 100% lossless storage.",
)
@click.option(
    "--enable-fts/--no-fts",
    default=True,
    show_default=True,
    help="Build SQLite FTS5 full-text search index table.",
)
@click.option(
    "--category-id",
    type=int,
    default=None,
    help="Scrape only a specific category ID.",
)
@click.option(
    "--max-pages",
    type=int,
    default=None,
    help="Maximum pages to scrape per category (useful for dry runs / testing).",
)
@click.option(
    "--compress",
    is_flag=True,
    default=False,
    help="Compress database to .tar.gz archive upon completion.",
)
@click.option(
    "-v", "--verbose",
    is_flag=True,
    default=False,
    help="Enable verbose DEBUG logging.",
)
def main(
    db_path: str,
    delay: float,
    instock_only: bool,
    include_raw_json: bool,
    enable_fts: bool,
    category_id: Optional[int],
    max_pages: Optional[int],
    compress: bool,
    verbose: bool,
) -> None:
    """Main CLI execution logic."""
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    click.echo("==================================================")
    click.echo("LCSC Product Database Builder")
    click.echo(f"  Output DB Path  : {db_path}")
    click.echo(f"  Request Delay   : {delay}s")
    click.echo(f"  In-Stock Only   : {instock_only}")
    click.echo(f"  Include Raw JSON: {include_raw_json}")
    click.echo(f"  Build FTS5 Index: {enable_fts}")
    if category_id:
        click.echo(f"  Category Filter : #{category_id}")
    if max_pages:
        click.echo(f"  Max Pages/Cat   : {max_pages}")
    click.echo("==================================================")

    api = LCSCApi(delay_seconds=delay)
    with LCSCDatabase(db_path=db_path) as db:
        scraper = LCSCScraper(
            api=api,
            db=db,
            instock_only=instock_only,
            include_raw_json=include_raw_json,
            enable_fts=enable_fts,
        )
        count = scraper.run(
            target_category_id=category_id,
            max_pages_per_category=max_pages,
        )

    click.echo(f"Successfully processed {count} products in {db_path}.")

    if compress:
        compress_database(db_path)


if __name__ == "__main__":
    main()
