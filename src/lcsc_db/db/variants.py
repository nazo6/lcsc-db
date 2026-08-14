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


FTS_STANDALONE_DDL = """
CREATE VIRTUAL TABLE products_fts USING fts5(
    lcsc_number,
    mfr_part_number,
    brand_name,
    package,
    description,
    first_category_name,
    second_category_name,
    third_category_name,
    brand_id UNINDEXED,
    category_id UNINDEXED,
    stock UNINDEXED,
    stock_sz UNINDEXED,
    stock_js UNINDEXED,
    stock_hk UNINDEXED,
    moq UNINDEXED,
    spq UNINDEXED,
    min_packet_number UNINDEXED,
    min_packet_unit UNINDEXED,
    product_unit UNINDEXED,
    product_arrange UNINDEXED,
    price_ladder UNINDEXED,
    pdf_url UNINDEXED,
    image_url UNINDEXED,
    product_images UNINDEXED,
    msl UNINDEXED,
    eccn UNINDEXED,
    url UNINDEXED,
    is_rohs UNINDEXED,
    is_hot UNINDEXED,
    is_reel UNINDEXED,
    reel_price UNINDEXED,
    is_sample UNINDEXED,
    is_discount UNINDEXED,
    is_pre_sale UNINDEXED,
    jlcpcb_stock UNINDEXED,
    jlcpcb_price_ladder UNINDEXED,
    jlcpcb_library_type UNINDEXED,
    jlcpcb_extra UNINDEXED,
    jlcpcb_last_updated UNINDEXED,
    last_updated UNINDEXED,
    tokenize="trigram"
);
"""

FTS_COLUMNS = [
    "lcsc_number",
    "mfr_part_number",
    "brand_name",
    "package",
    "description",
    "first_category_name",
    "second_category_name",
    "third_category_name",
    "brand_id",
    "category_id",
    "stock",
    "stock_sz",
    "stock_js",
    "stock_hk",
    "moq",
    "spq",
    "min_packet_number",
    "min_packet_unit",
    "product_unit",
    "product_arrange",
    "price_ladder",
    "pdf_url",
    "image_url",
    "product_images",
    "msl",
    "eccn",
    "url",
    "is_rohs",
    "is_hot",
    "is_reel",
    "reel_price",
    "is_sample",
    "is_discount",
    "is_pre_sale",
    "jlcpcb_stock",
    "jlcpcb_price_ladder",
    "jlcpcb_library_type",
    "jlcpcb_extra",
    "jlcpcb_last_updated",
    "last_updated",
]


def create_fts_only_variant(base_db_path: Path, output_db_path: Path) -> Path:
    """Create a standalone FTS search database containing products_fts with UNINDEXED columns and categories.

    The virtual table contains full-text search indexes on part numbers, brand, package, description,
    and categories, while storing all other product attributes as UNINDEXED columns for fast direct lookup.
    """
    if output_db_path.exists():
        output_db_path.unlink()

    output_db_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Creating standalone FTS database: %s", output_db_path)
    print(f"Creating FTS search database -> {output_db_path.name}")

    conn = sqlite3.connect(output_db_path, isolation_level=None)
    try:
        conn.execute("PRAGMA page_size = 4096;")
        conn.execute("PRAGMA synchronous = OFF;")
        conn.execute("PRAGMA journal_mode = OFF;")
        conn.execute("PRAGMA cache_size = -524288;")  # 512 MB memory cache
        conn.execute("PRAGMA temp_store = MEMORY;")
        conn.execute("PRAGMA mmap_size = 30000000000;")
        conn.execute("PRAGMA locking_mode = EXCLUSIVE;")

        # Create standalone FTS5 table
        print("  [1/5] Initializing FTS5 virtual table schema...")
        logger.info("Initializing FTS5 virtual table schema...")
        conn.execute(FTS_STANDALONE_DDL)

        # Disable automatic background segment merging during bulk insert
        conn.execute(
            "INSERT INTO products_fts(products_fts, rank) VALUES('automerge', 0);"
        )

        # Attach base database and copy searchable + unindexed columns
        conn.execute("ATTACH DATABASE ? AS src;", (str(base_db_path.resolve()),))
        conn.execute("PRAGMA src.cache_size = -262144;")  # 256 MB read cache for src
        conn.execute("PRAGMA src.mmap_size = 30000000000;")

        count_row = conn.execute(
            "SELECT count(*) FROM src.sqlite_master WHERE type='table' AND name='products';"
        ).fetchone()
        product_count = 0
        if count_row and count_row[0]:
            product_count = conn.execute(
                "SELECT count(*) FROM src.products;"
            ).fetchone()[0]

        print(
            f"  [2/5] Indexing {product_count:,} products into products_fts (trigram tokenization)..."
        )
        logger.info("Indexing %d products into products_fts...", product_count)

        conn.execute("BEGIN TRANSACTION;")

        cols_str = ", ".join(FTS_COLUMNS)
        conn.execute(
            f"""
            INSERT INTO products_fts ({cols_str})
            SELECT {cols_str}
            FROM src.products;
            """
        )

        # Copy categories table if it exists in src database
        has_categories = conn.execute(
            "SELECT 1 FROM src.sqlite_master WHERE type='table' AND name='categories';"
        ).fetchone()
        if has_categories:
            cat_count = conn.execute(
                "SELECT count(*) FROM src.categories;"
            ).fetchone()[0]
            print(f"  [3/5] Copying {cat_count:,} categories...")
            logger.info("Copying %d categories...", cat_count)
            conn.execute(
                """
                CREATE TABLE categories (
                    id INTEGER PRIMARY KEY,
                    parent_id INTEGER,
                    name_en TEXT NOT NULL,
                    name_cn TEXT,
                    code TEXT
                );
                """
            )
            conn.execute(
                """
                INSERT INTO categories (id, parent_id, name_en, name_cn, code)
                SELECT id, parent_id, name_en, name_cn, code FROM src.categories;
                """
            )
        else:
            print("  [3/5] Categories table not found in source, skipping...")

        conn.execute("COMMIT;")
        conn.execute("DETACH DATABASE src;")

        # Re-enable automerge default and optimize FTS index into a single B-tree segment
        print("  [4/5] Optimizing FTS5 index segments (merging into single B-tree)...")
        logger.info("Optimizing FTS5 index segments...")
        conn.execute(
            "INSERT INTO products_fts(products_fts, rank) VALUES('automerge', 4);"
        )
        conn.execute("INSERT INTO products_fts(products_fts) VALUES('optimize');")

        # Set journal mode to WAL for the final output database
        conn.execute("PRAGMA journal_mode = WAL;")
    finally:
        conn.close()

    # VACUUM to ensure clean compact pages
    print("  [5/5] Running VACUUM to compact database pages...")
    logger.info("Running VACUUM...")
    vacuum_conn = sqlite3.connect(output_db_path)
    try:
        vacuum_conn.execute("PRAGMA synchronous = OFF;")
        vacuum_conn.execute("PRAGMA cache_size = -524288;")
        vacuum_conn.execute("PRAGMA temp_store = MEMORY;")
        vacuum_conn.execute("VACUUM;")
    finally:
        vacuum_conn.close()

    size_mb = output_db_path.stat().st_size / (1024 * 1024)
    print(
        f"  ✓ Standalone FTS database created: {output_db_path.name} ({size_mb:.2f} MB)"
    )
    logger.info("FTS database created: %s (%.2f MB)", output_db_path.name, size_mb)

    return output_db_path


def create_sql_transform_variant(
    base_db_path: Path, output_db_path: Path, sql_statements: list[str]
) -> Path:
    """Create a variant by copying base_db_path and applying SQL statements."""
    if output_db_path.exists():
        output_db_path.unlink()

    output_db_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Creating variant -> {output_db_path.name} (copying base DB)...")
    logger.info("Creating variant %s from %s", output_db_path.name, base_db_path.name)
    shutil.copy2(base_db_path, output_db_path)

    conn = sqlite3.connect(output_db_path, isolation_level=None)
    try:
        conn.execute("PRAGMA synchronous = OFF;")
        conn.execute("PRAGMA cache_size = -524288;")
        conn.execute("PRAGMA temp_store = MEMORY;")
        for stmt in sql_statements:
            print(f"  Executing: {stmt.strip().splitlines()[0]}")
            conn.execute(stmt)
    finally:
        conn.close()

    size_mb = output_db_path.stat().st_size / (1024 * 1024)
    print(f"  ✓ Variant created: {output_db_path.name} ({size_mb:.2f} MB)")
    return output_db_path


# Variant definitions: name -> (description, factory function)
VARIANTS: dict[str, tuple[str, Callable[[Path, Path], Path]]] = {
    "fts_only": (
        "Standalone FTS5 trigram search index with all product attributes (UNINDEXED) & categories",
        create_fts_only_variant,
    ),
    "no_raw_json": (
        "Full relational database with raw_json cleared to NULL",
        lambda src, dst: create_sql_transform_variant(
            src, dst, ["UPDATE products SET raw_json = NULL;", "VACUUM;"]
        ),
    ),
    "minimal": (
        "Minimal relational database with raw_json cleared",
        lambda src, dst: create_sql_transform_variant(
            src,
            dst,
            [
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
