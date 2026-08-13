"""JLCPCB database syncer: download cache.sqlite3 from kicad-jlcpcb-tools and import into lcsc-db."""

import logging
import os
import sqlite3
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://bouni.github.io/kicad-jlcpcb-tools/"
SENTINEL_FILE = "cache_chunk_num.txt"
CACHE_PREFIX = "cache.sqlite3"


def download_jlcpcb_cache(
    target_dir: Path,
    max_workers: int = 4,
    log_cb: Callable[[str], None] | None = None,
) -> Path:
    """Download cache.sqlite3 chunks from kicad-jlcpcb-tools and unzip.

    Returns the path to unzipped ``cache.sqlite3``.
    """
    def _log(msg: str) -> None:
        logger.info(msg)
        if log_cb:
            log_cb(msg)

    target_dir.mkdir(parents=True, exist_ok=True)

    sentinel_url = BASE_URL + SENTINEL_FILE
    _log(f"Fetching JLCPCB chunk sentinel: {sentinel_url}")
    resp = requests.get(sentinel_url, timeout=30)
    resp.raise_for_status()
    total_chunks = int(resp.text.strip())
    _log(f"Total JLCPCB cache chunks to download: {total_chunks}")

    chunk_files: list[Path] = []

    def download_chunk(idx: int) -> Path:
        chunk_name = f"{CACHE_PREFIX}.zip.{idx:03d}"
        url = BASE_URL + chunk_name
        dest = target_dir / chunk_name
        _log(f"Downloading chunk {idx}/{total_chunks}: {url}")
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)
        return dest

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(download_chunk, i): i for i in range(1, total_chunks + 1)}
        for future in as_completed(futures):
            future.result()

    zip_file_path = target_dir / f"{CACHE_PREFIX}.zip"
    _log(f"Concatenating {total_chunks} chunks into {zip_file_path.name}...")
    with open(zip_file_path, "wb") as outfile:
        for i in range(1, total_chunks + 1):
            chunk_path = target_dir / f"{CACHE_PREFIX}.zip.{i:03d}"
            with open(chunk_path, "rb") as infile:
                outfile.write(infile.read())
            chunk_path.unlink()

    _log(f"Extracting {zip_file_path.name}...")
    with zipfile.ZipFile(zip_file_path, "r") as zf:
        zf.extractall(target_dir)

    zip_file_path.unlink()
    unzipped_db = target_dir / CACHE_PREFIX
    _log(f"Downloaded and extracted {unzipped_db} ({unzipped_db.stat().st_size:,} bytes)")
    return unzipped_db


def import_cache_db(
    cache_db_path: Path,
    target_db_path: Path,
    log_cb: Callable[[str], None] | None = None,
) -> int:
    """Import components and categories from cache.sqlite3 into lcsc.sqlite3.

    Returns the number of products imported/updated.
    """
    def _log(msg: str) -> None:
        logger.info(msg)
        if log_cb:
            log_cb(msg)

    _log(f"Starting batch import from {cache_db_path} -> {target_db_path}...")

    conn = sqlite3.connect(target_db_path)
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("ATTACH DATABASE ? AS cache_db;", (str(cache_db_path),))

        _log("Syncing categories from cache.sqlite3...")
        conn.execute("""
            INSERT INTO categories (id, name_en)
            SELECT id, subcategory
            FROM cache_db.categories
            WHERE 1
            ON CONFLICT(id) DO UPDATE SET
                name_en = excluded.name_en;
        """)

        _log("Syncing products from cache.sqlite3 (batch SQL import)...")
        cursor = conn.execute("""
            INSERT INTO products (
                product_id,
                lcsc_number,
                mfr_part_number,
                brand_id,
                brand_name,
                package,
                description,
                category_id,
                first_category_name,
                second_category_name,
                pdf_url,
                jlcpcb_stock,
                jlcpcb_price_ladder,
                jlcpcb_library_type,
                jlcpcb_extra,
                jlcpcb_last_updated
            )
            SELECT
                c.lcsc AS product_id,
                'C' || c.lcsc AS lcsc_number,
                c.mfr AS mfr_part_number,
                c.manufacturer_id AS brand_id,
                m.name AS brand_name,
                c.package AS package,
                c.description AS description,
                c.category_id AS category_id,
                cat.category AS first_category_name,
                cat.subcategory AS second_category_name,
                c.datasheet AS pdf_url,
                c.stock AS jlcpcb_stock,
                c.price AS jlcpcb_price_ladder,
                CASE
                    WHEN c.basic = 1 THEN 'Basic'
                    WHEN c.preferred = 1 THEN 'Preferred'
                    ELSE 'Extended'
                END AS jlcpcb_library_type,
                c.extra AS jlcpcb_extra,
                datetime(c.last_update, 'unixepoch') AS jlcpcb_last_updated
            FROM cache_db.components c
            LEFT JOIN cache_db.categories cat ON cat.id = c.category_id
            LEFT JOIN cache_db.manufacturers m ON m.id = c.manufacturer_id
            WHERE 1
            ON CONFLICT(lcsc_number) DO UPDATE SET
                mfr_part_number = excluded.mfr_part_number,
                brand_id = COALESCE(products.brand_id, excluded.brand_id),
                brand_name = COALESCE(products.brand_name, excluded.brand_name),
                package = COALESCE(products.package, excluded.package),
                description = COALESCE(products.description, excluded.description),
                category_id = COALESCE(products.category_id, excluded.category_id),
                first_category_name = COALESCE(products.first_category_name, excluded.first_category_name),
                second_category_name = COALESCE(products.second_category_name, excluded.second_category_name),
                pdf_url = COALESCE(products.pdf_url, excluded.pdf_url),
                jlcpcb_stock = excluded.jlcpcb_stock,
                jlcpcb_price_ladder = excluded.jlcpcb_price_ladder,
                jlcpcb_library_type = excluded.jlcpcb_library_type,
                jlcpcb_extra = excluded.jlcpcb_extra,
                jlcpcb_last_updated = excluded.jlcpcb_last_updated;
        """)

        affected = cursor.rowcount
        conn.commit()
        conn.execute("DETACH DATABASE cache_db;")
        _log(f"Batch import completed successfully ({affected:,} products processed).")
        return affected
    finally:
        conn.close()
