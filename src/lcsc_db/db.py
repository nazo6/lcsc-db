"""SQLite Database Manager for LCSC product catalog."""

import json
import logging
import sqlite3
from typing import Any, Optional, Set

from lcsc_db.models import Category, Product

logger = logging.getLogger(__name__)


class LCSCDatabase:
    """SQLite database manager for storing LCSC categories and products."""

    def __init__(self, db_path: str = "lcsc.sqlite3") -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        if self.conn:
            self.conn.close()

    def __enter__(self) -> "LCSCDatabase":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def init_schema(self, include_raw_json: bool = True, enable_fts: bool = True) -> None:
        """Create tables, indexes, and optional FTS5 virtual table."""
        with self.conn:
            # Categories table
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY,
                    parent_id INTEGER,
                    name_en TEXT NOT NULL,
                    name_cn TEXT,
                    code TEXT
                );
                """
            )

            # Products table (Lossless Store)
            raw_json_column = "raw_json TEXT," if include_raw_json else ""
            self.conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS products (
                    product_id INTEGER PRIMARY KEY,
                    lcsc_number TEXT UNIQUE NOT NULL,
                    mfr_part_number TEXT NOT NULL,
                    brand_id INTEGER,
                    brand_name TEXT,
                    package TEXT,
                    description TEXT,
                    category_id INTEGER,
                    first_category_name TEXT,
                    second_category_name TEXT,
                    third_category_name TEXT,
                    stock INTEGER DEFAULT 0,
                    stock_sz INTEGER DEFAULT 0,
                    stock_js INTEGER DEFAULT 0,
                    stock_hk INTEGER DEFAULT 0,
                    moq INTEGER DEFAULT 1,
                    spq INTEGER DEFAULT 1,
                    min_packet_number INTEGER,
                    min_packet_unit TEXT,
                    product_unit TEXT,
                    product_arrange TEXT,
                    price_ladder TEXT,
                    pdf_url TEXT,
                    image_url TEXT,
                    product_images TEXT,
                    msl TEXT,
                    eccn TEXT,
                    url TEXT,
                    is_rohs INTEGER DEFAULT 0,
                    is_hot INTEGER DEFAULT 0,
                    is_reel INTEGER DEFAULT 0,
                    reel_price REAL DEFAULT 0.0,
                    is_sample INTEGER DEFAULT 0,
                    is_discount INTEGER DEFAULT 0,
                    is_pre_sale INTEGER DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    {raw_json_column}
                    FOREIGN KEY(category_id) REFERENCES categories(id)
                );
                """
            )

            # Product parameters table
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS product_params (
                    product_id INTEGER,
                    param_name TEXT,
                    param_value TEXT,
                    FOREIGN KEY(product_id) REFERENCES products(product_id)
                );
                """
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_product_params_id ON product_params(product_id);"
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_products_lcsc ON products(lcsc_number);"
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_products_mfr ON products(mfr_part_number);"
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_products_cat ON products(category_id);"
            )

            if enable_fts:
                # FTS5 External Content Table
                self.conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS products_fts USING fts5(
                        lcsc_number,
                        mfr_part_number,
                        brand_name,
                        package,
                        description,
                        content='products',
                        content_rowid='product_id'
                    );
                    """
                )

            # Scrape progress tracking tables
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scrape_progress (
                    category_id INTEGER NOT NULL,
                    brand_id INTEGER NOT NULL DEFAULT 0,
                    keyword TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'completed',
                    total_rows INTEGER DEFAULT 0,
                    scraped_count INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (category_id, brand_id, keyword)
                );
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scraped_seen_products (
                    product_id INTEGER PRIMARY KEY
                );
                """
            )

    def upsert_categories(self, categories_list: list[Category]) -> None:
        """Insert or update categories."""
        query = """
        INSERT INTO categories (id, parent_id, name_en, name_cn, code)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            parent_id=excluded.parent_id,
            name_en=excluded.name_en,
            name_cn=excluded.name_cn,
            code=excluded.code;
        """
        rows = [
            (cat.category_id, cat.parent_id, cat.name_en, cat.name_cn, cat.code)
            for cat in categories_list
        ]
        with self.conn:
            self.conn.executemany(query, rows)

    def upsert_products(
        self, products: list[Product], include_raw_json: bool = True
    ) -> None:
        """Insert or update products and their parameters."""
        if not products:
            return

        cols = [
            "product_id",
            "lcsc_number",
            "mfr_part_number",
            "brand_id",
            "brand_name",
            "package",
            "description",
            "category_id",
            "first_category_name",
            "second_category_name",
            "third_category_name",
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
        ]
        if include_raw_json:
            cols.append("raw_json")

        col_names = ", ".join(cols)
        placeholders = ", ".join(["?"] * len(cols))
        update_set = ", ".join([f"{c}=excluded.{c}" for c in cols if c != "product_id"])

        query = f"""
        INSERT INTO products ({col_names})
        VALUES ({placeholders})
        ON CONFLICT(product_id) DO UPDATE SET
            {update_set},
            last_updated=CURRENT_TIMESTAMP;
        """

        product_rows = []
        param_rows = []

        for p in products:
            pid = p.product_id
            if not pid or not p.lcsc_number:
                continue

            row = [
                pid,
                p.lcsc_number,
                p.mfr_part_number,
                p.brand_id,
                p.brand_name,
                p.package,
                p.description,
                p.category_id,
                p.first_category_name,
                p.second_category_name,
                p.third_category_name,
                p.stock or 0,
                p.stock_sz or 0,
                p.stock_js or 0,
                p.stock_hk or 0,
                p.moq or 1,
                p.spq or 1,
                p.min_packet_number,
                p.min_packet_unit,
                p.product_unit,
                p.product_arrange,
                json.dumps(
                    [pl.model_dump(by_alias=True) for pl in (p.price_ladder or [])],
                    ensure_ascii=False,
                ),
                p.pdf_url,
                p.image_url,
                json.dumps(p.product_images or [], ensure_ascii=False),
                p.msl,
                p.eccn,
                p.url,
                1 if p.is_rohs else 0,
                1 if p.is_hot else 0,
                1 if p.is_reel else 0,
                float(p.reel_price or 0.0),
                1 if p.is_sample else 0,
                1 if p.is_discount else 0,
                1 if p.is_pre_sale else 0,
            ]
            if include_raw_json:
                row.append(
                    json.dumps(p.model_dump(mode="json", by_alias=True, exclude_none=True), ensure_ascii=False)
                )

            product_rows.append(row)

            # Parameters
            for param in p.params or []:
                p_name = param.name
                p_val = param.value
                if p_name and p_val:
                    param_rows.append((pid, str(p_name), str(p_val)))

        with self.conn:
            self.conn.executemany(query, product_rows)

            # Refresh parameters for inserted products
            pids = [r[0] for r in product_rows]
            if pids:
                pid_placeholders = ", ".join(["?"] * len(pids))
                self.conn.execute(
                    f"DELETE FROM product_params WHERE product_id IN ({pid_placeholders});", pids
                )
                if param_rows:
                    self.conn.executemany(
                        "INSERT INTO product_params (product_id, param_name, param_value) VALUES (?, ?, ?);",
                        param_rows,
                    )

    def rebuild_fts(self) -> None:
        """Rebuild FTS5 index for full-text search."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='products_fts';"
        )
        if cursor.fetchone():
            with self.conn:
                self.conn.execute("INSERT INTO products_fts(products_fts) VALUES('rebuild');")

    def mark_unseen_stock_zero(self, seen_product_ids: Set[int]) -> None:
        """Mark products stock as 0 if they were not seen in the current scrape run."""
        if not seen_product_ids:
            return
        with self.conn:
            # Create temp table for seen ids
            self.conn.execute(
                "CREATE TEMP TABLE IF NOT EXISTS temp_seen (product_id INTEGER PRIMARY KEY);"
            )
            self.conn.execute("DELETE FROM temp_seen;")
            self.conn.executemany(
                "INSERT INTO temp_seen VALUES (?);", [(pid,) for pid in seen_product_ids]
            )
            self.conn.execute(
                """
                UPDATE products
                SET stock = 0, stock_sz = 0, stock_js = 0, stock_hk = 0
                WHERE product_id NOT IN (SELECT product_id FROM temp_seen);
                """
            )
            self.conn.execute("DROP TABLE temp_seen;")

    def vacuum_and_optimize(self) -> None:
        """Optimize and vacuum database."""
        self.conn.execute("PRAGMA optimize;")
        self.conn.execute("VACUUM;")

    def is_query_completed(
        self,
        category_id: int,
        brand_id: Optional[int] = None,
        keyword: Optional[str] = None,
    ) -> bool:
        """Check if a specific category query has been completed in the current scrape pass."""
        b_id = brand_id or 0
        kw = keyword or ""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT 1 FROM scrape_progress
            WHERE category_id = ? AND brand_id = ? AND keyword = ? AND status = 'completed';
            """,
            (category_id, b_id, kw),
        )
        return cursor.fetchone() is not None

    def mark_query_completed(
        self,
        category_id: int,
        brand_id: Optional[int] = None,
        keyword: Optional[str] = None,
        total_rows: int = 0,
        scraped_count: int = 0,
    ) -> None:
        """Mark a category query as completed in scrape_progress."""
        b_id = brand_id or 0
        kw = keyword or ""
        query = """
        INSERT INTO scrape_progress (category_id, brand_id, keyword, status, total_rows, scraped_count, updated_at)
        VALUES (?, ?, ?, 'completed', ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(category_id, brand_id, keyword) DO UPDATE SET
            status = 'completed',
            total_rows = excluded.total_rows,
            scraped_count = excluded.scraped_count,
            updated_at = CURRENT_TIMESTAMP;
        """
        with self.conn:
            self.conn.execute(query, (category_id, b_id, kw, total_rows, scraped_count))

    def record_seen_products(self, product_ids: Set[int]) -> None:
        """Record product IDs as seen during the current scrape pass."""
        if not product_ids:
            return
        rows = [(pid,) for pid in product_ids]
        with self.conn:
            self.conn.executemany(
                "INSERT OR IGNORE INTO scraped_seen_products (product_id) VALUES (?);", rows
            )

    def has_incomplete_progress(self) -> bool:
        """Check if there is active in-progress scrape data in progress tables."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scrape_progress';")
        if not cursor.fetchone():
            return False
        cursor.execute("SELECT COUNT(*) FROM scrape_progress;")
        return cursor.fetchone()[0] > 0

    def clear_scrape_progress(self) -> None:
        """Clear all scrape progress and seen products tables after a full scrape cycle finishes."""
        with self.conn:
            self.conn.execute("DELETE FROM scrape_progress;")
            self.conn.execute("DELETE FROM scraped_seen_products;")

    def mark_unseen_stock_zero_from_db(self) -> int:
        """Mark products stock as 0 if they were not seen in the current multi-stage scrape run."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM scraped_seen_products;")
        seen_count = cursor.fetchone()[0]
        if seen_count == 0:
            return 0

        with self.conn:
            cursor = self.conn.execute(
                """
                UPDATE products
                SET stock = 0, stock_sz = 0, stock_js = 0, stock_hk = 0
                WHERE product_id NOT IN (SELECT product_id FROM scraped_seen_products);
                """
            )
            return cursor.rowcount

