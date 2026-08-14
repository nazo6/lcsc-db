"""CLI entrypoint for lcsc-db command using pydantic-settings."""

import logging
import sys
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, CliApp, CliSubCommand, SettingsConfigDict

from lcsc_db.api import LCSCApi, LCSCApiConfig
from lcsc_db.db import VARIANTS, LCSCDatabase, compress_file, generate_all_variants
from lcsc_db.release import run_release_manager
from lcsc_db.sync import LCSCScraper, ScraperConfig, download_jlcpcb_cache


def compress_database(db_path: str) -> str:
    """Compress database file to .tar.xz archive using xz/tar if available, falling back to tarfile."""
    archive_path = compress_file(Path(db_path))
    return str(archive_path)


class SyncJLCPCBSettings(BaseModel):
    """Download JLCPCB cache database and sync ~7.12M components into SQLite."""

    db_path: str = Field(default="lcsc.sqlite3", description="Output SQLite database file path.")
    cache_dir: str = Field(
        default=".jlcpcb_cache",
        description="Temporary directory to download JLCPCB cache chunks.",
    )
    compress: bool = Field(
        default=False,
        description="Compress database to .tar.xz archive upon completion.",
    )
    verbose: bool = Field(default=False, description="Enable verbose DEBUG logging.")

    def cli_cmd(self) -> None:
        """Execute JLCPCB cache download & database sync."""
        log_level = logging.DEBUG if self.verbose else logging.INFO
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )

        print("==================================================")
        print("JLCPCB Database Syncer -> LCSC Database")
        print(f"  Output DB Path  : {self.db_path}")
        print(f"  Cache Directory : {self.cache_dir}")
        print("==================================================")

        cache_dir = Path(self.cache_dir)
        cache_path = download_jlcpcb_cache(target_dir=cache_dir)

        with LCSCDatabase(db_path=self.db_path) as db:
            db.init_schema()
            count = db.import_jlcpcb_cache(cache_path)
            db.vacuum_and_optimize()
            print(f"Successfully synced {count:,} JLCPCB products into {self.db_path}.")

        if self.compress:
            compress_database(self.db_path)


class ScrapeLCSCSettings(BaseModel):
    """Scrape real-time stock and prices from LCSC API."""

    db_path: str = Field(default="lcsc.sqlite3", description="Output SQLite database file path.")
    delay: float = Field(default=2.0, description="Delay in seconds between API requests.")
    instock_only: bool = Field(
        default=True,
        description="Fetch only currently in-stock products.",
    )
    include_raw_json: bool = Field(
        default=True,
        description="Save raw API JSON response.",
    )
    category_id: int | None = Field(
        default=None,
        description="Scrape only a specific category ID.",
    )
    max_pages: int | None = Field(
        default=None,
        description="Maximum pages to scrape per category.",
    )
    compress: bool = Field(
        default=False,
        description="Compress database to .tar.xz archive upon completion.",
    )
    verbose: bool = Field(default=False, description="Enable verbose DEBUG logging.")

    def cli_cmd(self) -> None:
        """Execute LCSC API scraper."""
        log_level = logging.DEBUG if self.verbose else logging.INFO
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )

        print("==================================================")
        print("LCSC Product Database Scraper")
        print(f"  Output DB Path  : {self.db_path}")
        print(f"  Request Delay   : {self.delay}s")
        print(f"  In-Stock Only   : {self.instock_only}")
        print(f"  Include Raw JSON: {self.include_raw_json}")
        if self.category_id:
            print(f"  Category Filter : #{self.category_id}")
        if self.max_pages:
            print(f"  Max Pages/Cat   : {self.max_pages}")
        print("==================================================")

        api = LCSCApi(LCSCApiConfig(delay_seconds=self.delay))
        with LCSCDatabase(db_path=self.db_path) as db:
            db.init_schema()
            config = ScraperConfig(
                instock_only=self.instock_only,
                include_raw_json=self.include_raw_json,
            )
            scraper = LCSCScraper(api=api, db=db, config=config)
            count = scraper.run(
                target_category_id=self.category_id,
                max_pages_per_category=self.max_pages,
            )

            expected_str = (
                f"{scraper.total_expected_products:,}"
                if scraper.total_expected_products > 0
                else "N/A"
            )
            print(
                f"Successfully processed {count:,} unique products in {self.db_path} "
                f"(Expected: {expected_str} products, Fetched: {scraper.total_fetched_items:,} items)."
            )

        if self.compress:
            compress_database(self.db_path)


class CreateVariantsSettings(BaseModel):
    """Generate optimized database variants (e.g. fts_only, no_raw_json, minimal)."""

    db_path: str = Field(default="lcsc.sqlite3", description="Input SQLite database file path.")
    output_dir: str | None = Field(
        default=None,
        description="Output directory for generated variants.",
    )
    variants: list[str] = Field(
        default_factory=lambda: ["fts_only"],
        description=f"List of variants to generate (choices: {list(VARIANTS.keys()) + ['all']}).",
    )
    compress: bool = Field(
        default=True,
        description="Compress generated variants to .tar.xz archive.",
    )
    verbose: bool = Field(default=False, description="Enable verbose DEBUG logging.")

    def cli_cmd(self) -> None:
        """Execute database variant generation."""
        log_level = logging.DEBUG if self.verbose else logging.INFO
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
        selected = None if "all" in self.variants else self.variants
        generate_all_variants(
            base_db_path=Path(self.db_path),
            output_dir=Path(self.output_dir) if self.output_dir else None,
            selected_variants=selected,
            compress=self.compress,
        )


class UpdateReleaseSettings(BaseModel):
    """Upload files to GitHub Release and update release notes size table."""

    tag: str = Field(default="latest", description="Release tag name (default: latest).")
    title: str = Field(
        default="LCSC Product Database (Latest)",
        description="Release title.",
    )
    files: list[str] = Field(
        default_factory=list,
        description="List of files (.sqlite3 or .tar.xz) to inspect and upload.",
    )
    dry_run: bool = Field(
        default=False,
        description="Print updated release notes without calling GitHub CLI.",
    )
    verbose: bool = Field(default=False, description="Enable verbose DEBUG logging.")

    def cli_cmd(self) -> None:
        """Execute GitHub Release update and size stats logging."""
        log_level = logging.DEBUG if self.verbose else logging.INFO
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
        run_release_manager(
            tag=self.tag,
            title=self.title,
            target_files=[Path(f) for f in self.files],
            dry_run=self.dry_run,
        )


class CLI(BaseSettings):
    """Scraper and SQLite database builder for LCSC and JLCPCB electronics components."""

    model_config = SettingsConfigDict(
        cli_prog_name="lcsc-db",
        cli_kebab_case=True,
        cli_implicit_flags="dual",
        cli_use_class_docs_for_groups=True,
    )

    sync_jlcpcb: Annotated[
        CliSubCommand[SyncJLCPCBSettings],
        Field(
            alias="sync-jlcpcb",
            description="Download JLCPCB cache database and sync ~7.12M components into SQLite.",
        ),
    ]
    scrape_lcsc: Annotated[
        CliSubCommand[ScrapeLCSCSettings],
        Field(
            alias="scrape-lcsc",
            description="Scrape real-time stock and prices from LCSC API.",
        ),
    ]
    create_variants: Annotated[
        CliSubCommand[CreateVariantsSettings],
        Field(
            alias="create-variants",
            description="Generate optimized database variants (e.g. fts_only, no_raw_json, minimal).",
        ),
    ]
    update_release: Annotated[
        CliSubCommand[UpdateReleaseSettings],
        Field(
            alias="update-release",
            description="Upload files to GitHub Release and update release notes size table.",
        ),
    ]

    def cli_cmd(self) -> None:
        """Dispatch execution to selected subcommand."""
        if self.sync_jlcpcb is not None:
            self.sync_jlcpcb.cli_cmd()
        elif self.scrape_lcsc is not None:
            self.scrape_lcsc.cli_cmd()
        elif self.create_variants is not None:
            self.create_variants.cli_cmd()
        elif self.update_release is not None:
            self.update_release.cli_cmd()
        else:
            print("Please specify a subcommand. Run with --help for usage.")


def main(args: list[str] | None = None) -> None:
    """CLI entrypoint."""
    cli_args = args if args is not None else sys.argv[1:]
    CliApp.run(CLI, cli_args=cli_args)


if __name__ == "__main__":
    main()
