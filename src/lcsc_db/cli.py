"""CLI entrypoint for lcsc-db command."""

import logging
import os
import tarfile

from pydantic import Field
from pydantic_settings import BaseSettings, CliApp, SettingsConfigDict

from lcsc_db.api import LCSCApi, LCSCApiConfig
from lcsc_db.db import LCSCDatabase
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


class Settings(BaseSettings):
    """LCSC Product Catalog Database Builder CLI"""

    model_config = SettingsConfigDict(
        cli_prog_name="lcsc-db",
        cli_kebab_case=True,
        cli_implicit_flags="dual",
        cli_hide_none_type=True,
    )

    db_path: str = Field("lcsc.sqlite3", description="Path to output SQLite database file.")
    delay: float = Field(2.0, description="Delay in seconds between API requests.")
    instock_only: bool = Field(
        True, description="Fetch only currently in-stock products to save ~70% API calls vs fetch all parts."
    )
    include_raw_json: bool = Field(
        True, description="Save raw API JSON response in raw_json column for 100% lossless storage."
    )
    enable_fts: bool = Field(True, description="Build SQLite FTS5 full-text search index table.")
    category_id: int | None = Field(None, description="Scrape only a specific category ID.")
    max_pages: int | None = Field(
        None, description="Maximum pages to scrape per category (useful for dry runs / testing)."
    )
    compress: bool = Field(False, description="Compress database to .tar.gz archive upon completion.")
    verbose: bool = Field(False, description="Enable verbose DEBUG logging.")

    def cli_cmd(self) -> None:
        run(self)


def run(settings: Settings) -> None:
    """Main CLI execution logic."""
    log_level = logging.DEBUG if settings.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print("==================================================")
    print("LCSC Product Database Builder")
    print(f"  Output DB Path  : {settings.db_path}")
    print(f"  Request Delay   : {settings.delay}s")
    print(f"  In-Stock Only   : {settings.instock_only}")
    print(f"  Include Raw JSON: {settings.include_raw_json}")
    print(f"  Build FTS5 Index: {settings.enable_fts}")
    if settings.category_id:
        print(f"  Category Filter : #{settings.category_id}")
    if settings.max_pages:
        print(f"  Max Pages/Cat   : {settings.max_pages}")
    print("==================================================")

    api = LCSCApi(LCSCApiConfig(delay_seconds=settings.delay))
    with LCSCDatabase(db_path=settings.db_path) as db:
        scraper = LCSCScraper(
            api=api,
            db=db,
            config=ScraperConfig.model_validate(settings.model_dump()),
        )
        count = scraper.run(
            target_category_id=settings.category_id,
            max_pages_per_category=settings.max_pages,
        )

    print(f"Successfully processed {count} products in {settings.db_path}.")

    if settings.compress:
        compress_database(settings.db_path)


def main() -> None:
    CliApp.run(Settings)


if __name__ == "__main__":
    main()
