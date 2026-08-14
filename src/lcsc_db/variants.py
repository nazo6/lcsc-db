"""SQLite database variants generator.

Generates optimized variants from a full database (e.g. standalone FTS-only index,
no raw_json, no FTS, minimal).
"""

import logging
import os
import shutil
import sqlite3
import subprocess
import tarfile
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


def compress_file(file_path: Path) -> Path:
    """Compress a file to .tar.xz using xz/tar if available, falling back to python tarfile."""
    archive_path = file_path.with_name(f"{file_path.name}.tar.xz")
    print(f"Compressing {file_path.name} -> {archive_path.name}...")

    parent_dir = file_path.parent
    archive_path_obj = archive_path.resolve()

    compressed_fast = False
    if shutil.which("tar") is not None and shutil.which("xz") is not None:
        try:
            cmd = ["tar", "-I", "xz -T0", "-cf", str(archive_path_obj), file_path.name]
            subprocess.run(cmd, cwd=str(parent_dir), check=True, capture_output=True)
            compressed_fast = True
        except Exception as e:
            logger.debug("Fast tar compression failed: %s", e)
            compressed_fast = False

    if not compressed_fast:
        with tarfile.open(archive_path, "w:xz") as tar:
            tar.add(file_path, arcname=file_path.name)

    size_mb = os.path.getsize(archive_path) / (1024 * 1024)
    print(f"Compressed archive created: {archive_path.name} ({size_mb:.2f} MB)")
    return archive_path


def create_fts_only_variant(base_db_path: Path, output_db_path: Path) -> Path:
    """Create a standalone FTS-only database containing only the products_fts virtual table.

    The virtual table does not use external content ('content=' parameter),
    making it completely self-contained and significantly smaller.
    """
    if output_db_path.exists():
        output_db_path.unlink()

    output_db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(output_db_path, isolation_level=None)
    try:
        conn.execute("PRAGMA page_size = 4096;")
        conn.execute("PRAGMA journal_mode = WAL;")

        # Create standalone FTS5 table
        conn.execute(
            """
            CREATE VIRTUAL TABLE products_fts USING fts5(
                lcsc_number,
                mfr_part_number,
                brand_name,
                package,
                description,
                first_category_name,
                second_category_name,
                tokenize="trigram"
            );
            """
        )

        # Attach base database and copy searchable columns
        conn.execute("ATTACH DATABASE ? AS src;", (str(base_db_path.resolve()),))
        conn.execute("BEGIN TRANSACTION;")
        conn.execute(
            """
            INSERT INTO products_fts (
                lcsc_number,
                mfr_part_number,
                brand_name,
                package,
                description,
                first_category_name,
                second_category_name
            )
            SELECT
                lcsc_number,
                mfr_part_number,
                brand_name,
                package,
                description,
                first_category_name,
                second_category_name
            FROM src.products;
            """
        )
        conn.execute("COMMIT;")
        conn.execute("DETACH DATABASE src;")

        # Optimize FTS and database file
        conn.execute("INSERT INTO products_fts(products_fts) VALUES('optimize');")
    finally:
        conn.close()

    # VACUUM to ensure clean compact pages
    vacuum_conn = sqlite3.connect(output_db_path)
    try:
        vacuum_conn.execute("VACUUM;")
    finally:
        vacuum_conn.close()

    return output_db_path


def create_sql_transform_variant(
    base_db_path: Path, output_db_path: Path, sql_statements: list[str]
) -> Path:
    """Create a variant by copying base_db_path and applying SQL statements."""
    if output_db_path.exists():
        output_db_path.unlink()

    output_db_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(base_db_path, output_db_path)

    conn = sqlite3.connect(output_db_path, isolation_level=None)
    try:
        for stmt in sql_statements:
            conn.execute(stmt)
    finally:
        conn.close()

    return output_db_path


# Variant definitions: name -> (description, factory function)
VARIANTS: dict[str, tuple[str, Callable[[Path, Path], Path]]] = {
    "fts_only": (
        "Standalone FTS5 trigram search index only (no products/raw_json tables)",
        create_fts_only_variant,
    ),
    "no_raw_json": (
        "Full database with FTS5, but raw_json cleared to NULL",
        lambda src, dst: create_sql_transform_variant(
            src, dst, ["UPDATE products SET raw_json = NULL;", "VACUUM;"]
        ),
    ),
    "no_fts": (
        "Full database without FTS5 index table",
        lambda src, dst: create_sql_transform_variant(
            src, dst, ["DROP TABLE IF EXISTS products_fts;", "VACUUM;"]
        ),
    ),
    "minimal": (
        "Minimal database without FTS5 index and raw_json cleared",
        lambda src, dst: create_sql_transform_variant(
            src,
            dst,
            [
                "DROP TABLE IF EXISTS products_fts;",
                "UPDATE products SET raw_json = NULL;",
                "VACUUM;",
            ],
        ),
    ),
}


def generate_variant(
    base_db_path: Path,
    variant_name: str,
    output_path: Path | None = None,
    compress: bool = True,
) -> dict:
    """Generate a single database variant.

    Returns dict with paths and file sizes.
    """
    if variant_name not in VARIANTS:
        raise ValueError(
            f"Unknown variant '{variant_name}'. Available: {list(VARIANTS.keys())}"
        )

    desc, generator = VARIANTS[variant_name]
    if output_path is None:
        stem = base_db_path.stem
        output_path = base_db_path.parent / f"{stem}_{variant_name}.sqlite3"

    print(f"Generating variant '{variant_name}' ({desc}) -> {output_path}...")
    db_file = generator(base_db_path, output_path)
    db_bytes = db_file.stat().st_size

    archive_file = None
    archive_bytes = None
    if compress:
        archive_file = compress_file(db_file)
        archive_bytes = archive_file.stat().st_size

    return {
        "variant": variant_name,
        "description": desc,
        "db_path": db_file,
        "db_size_bytes": db_bytes,
        "archive_path": archive_file,
        "archive_size_bytes": archive_bytes,
    }


def generate_all_variants(
    base_db_path: Path,
    output_dir: Path | None = None,
    selected_variants: list[str] | None = None,
    compress: bool = True,
) -> list[dict]:
    """Generate multiple variants for a given database."""
    target_variants = selected_variants or list(VARIANTS.keys())
    results = []

    out_dir = output_dir or base_db_path.parent
    stem = base_db_path.stem

    for name in target_variants:
        out_path = out_dir / f"{stem}_{name}.sqlite3"
        res = generate_variant(
            base_db_path=base_db_path,
            variant_name=name,
            output_path=out_path,
            compress=compress,
        )
        results.append(res)

    return results
