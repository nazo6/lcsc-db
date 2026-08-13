"""SQLite Database Manager for LCSC product catalog."""

import json
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Set

from alembic import command
from alembic.config import Config
from sqlalchemy import delete, func, inspect, select, text, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session, create_engine

from lcsc_db.models import Category, Product
from lcsc_db.schema import (
    FTS_DDL,
    CategoryRecord,
    ProductParamRecord,
    ProductRecord,
    ScrapeProgressRecord,
    ScrapedSeenProductRecord,
)

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
BASELINE_REVISION = "0001"


def _alembic_config(db_path: str) -> Config:
    cfg = Config(str(MIGRATIONS_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


class LCSCDatabase:
    """SQLite database manager for storing LCSC categories and products.

    Schema is managed by Alembic migrations (see ``lcsc_db.migrations``);
    data access uses SQLModel/SQLAlchemy.
    """

    def __init__(self, db_path: str = "lcsc.sqlite3") -> None:
        self.db_path = db_path
        self.engine = create_engine(f"sqlite:///{db_path}")

    def close(self) -> None:
        self.engine.dispose()

    def __enter__(self) -> "LCSCDatabase":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    @contextmanager
    def _tx(self):
        with Session(self.engine) as session:
            with session.begin():
                yield session

    def _has_table(self, table_name: str) -> bool:
        return inspect(self.engine).has_table(table_name)

    def _ensure_legacy_columns(self) -> None:
        """Add columns that older pre-migration schemas lacked (idempotent)."""
        with self.engine.connect() as conn:
            cols = {row[0] for row in conn.exec_driver_sql("PRAGMA table_info(products)")}
            if "raw_json" not in cols:
                conn.exec_driver_sql("ALTER TABLE products ADD COLUMN raw_json TEXT")
            conn.commit()

    def init_schema(self, enable_fts: bool = True) -> None:
        """Create tables, indexes, and optional FTS5 virtual table via migrations."""
        cfg = _alembic_config(self.db_path)
        if not self._has_table("alembic_version"):
            if self._has_table("products"):
                # Legacy database created before Alembic-managed schema:
                # bring it to the baseline, then let migrations apply any newer deltas.
                self._ensure_legacy_columns()
                command.stamp(cfg, BASELINE_REVISION)
        command.upgrade(cfg, "head")
        if enable_fts:
            with self.engine.connect() as conn:
                conn.exec_driver_sql(FTS_DDL)
                conn.commit()

    def upsert_categories(self, categories_list: list[Category]) -> None:
        """Insert or update categories."""
        insert_stmt = sqlite_insert(CategoryRecord)
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=[CategoryRecord.id],
            set_={
                "parent_id": insert_stmt.excluded.parent_id,
                "name_en": insert_stmt.excluded.name_en,
                "name_cn": insert_stmt.excluded.name_cn,
                "code": insert_stmt.excluded.code,
            },
        )
        rows = [
            {
                "id": cat.category_id,
                "parent_id": cat.parent_id,
                "name_en": cat.name_en,
                "name_cn": cat.name_cn,
                "code": cat.code,
            }
            for cat in categories_list
        ]
        with self._tx() as session:
            if rows:
                session.execute(stmt, rows)

    def upsert_products(
        self, products: list[Product], include_raw_json: bool = True
    ) -> None:
        """Insert or update products and their parameters.

        The ``raw_json`` column always exists in the schema; ``include_raw_json``
        controls whether the raw payload is written (or left as NULL).
        """
        if not products:
            return

        update_cols = [
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
            update_cols.append("raw_json")

        insert_stmt = sqlite_insert(ProductRecord)
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=[ProductRecord.product_id],
            set_={
                **{c: getattr(insert_stmt.excluded, c) for c in update_cols},
                "last_updated": text("CURRENT_TIMESTAMP"),
            },
        )

        product_rows = []
        param_rows = []

        for p in products:
            pid = p.product_id
            if not pid or not p.lcsc_number:
                continue

            row = {
                "product_id": pid,
                "lcsc_number": p.lcsc_number,
                "mfr_part_number": p.mfr_part_number,
                "brand_id": p.brand_id,
                "brand_name": p.brand_name,
                "package": p.package,
                "description": p.description,
                "category_id": p.category_id,
                "first_category_name": p.first_category_name,
                "second_category_name": p.second_category_name,
                "third_category_name": p.third_category_name,
                "stock": p.stock or 0,
                "stock_sz": p.stock_sz or 0,
                "stock_js": p.stock_js or 0,
                "stock_hk": p.stock_hk or 0,
                "moq": p.moq or 1,
                "spq": p.spq or 1,
                "min_packet_number": p.min_packet_number,
                "min_packet_unit": p.min_packet_unit,
                "product_unit": p.product_unit,
                "product_arrange": p.product_arrange,
                "price_ladder": json.dumps(
                    [pl.model_dump(by_alias=True) for pl in (p.price_ladder or [])],
                    ensure_ascii=False,
                ),
                "pdf_url": p.pdf_url,
                "image_url": p.image_url,
                "product_images": json.dumps(p.product_images or [], ensure_ascii=False),
                "msl": p.msl,
                "eccn": p.eccn,
                "url": p.url,
                "is_rohs": 1 if p.is_rohs else 0,
                "is_hot": 1 if p.is_hot else 0,
                "is_reel": 1 if p.is_reel else 0,
                "reel_price": float(p.reel_price or 0.0),
                "is_sample": 1 if p.is_sample else 0,
                "is_discount": 1 if p.is_discount else 0,
                "is_pre_sale": 1 if p.is_pre_sale else 0,
            }
            if include_raw_json:
                row["raw_json"] = json.dumps(
                    p.model_dump(mode="json", by_alias=True, exclude_none=True),
                    ensure_ascii=False,
                )
            product_rows.append(row)

            for param in p.params or []:
                if param.name and param.value:
                    param_rows.append(
                        {
                            "product_id": pid,
                            "param_name": str(param.name),
                            "param_value": str(param.value),
                        }
                    )

        with self._tx() as session:
            if product_rows:
                session.execute(stmt, product_rows)

                # Refresh parameters for inserted products
                pids = [r["product_id"] for r in product_rows]
                session.execute(
                    delete(ProductParamRecord).where(ProductParamRecord.product_id.in_(pids))
                )
                if param_rows:
                    session.execute(sqlite_insert(ProductParamRecord), param_rows)

    def rebuild_fts(self) -> None:
        """Rebuild FTS5 index for full-text search."""
        if not self._has_table("products_fts"):
            return
        with self._tx() as session:
            session.execute(text("INSERT INTO products_fts(products_fts) VALUES('rebuild');"))

    def vacuum_and_optimize(self) -> None:
        """Optimize and vacuum database."""
        with self.engine.raw_connection() as conn:
            conn.execute("PRAGMA optimize;")
            conn.execute("VACUUM;")

    def is_query_completed(
        self,
        category_id: int,
        brand_id: Optional[int] = None,
        keyword: Optional[str] = None,
    ) -> bool:
        """Check if a specific category query has been completed in the current scrape pass."""
        b_id = brand_id or 0
        kw = keyword or ""
        stmt = select(ScrapeProgressRecord).where(
            ScrapeProgressRecord.category_id == category_id,
            ScrapeProgressRecord.brand_id == b_id,
            ScrapeProgressRecord.keyword == kw,
            ScrapeProgressRecord.status == "completed",
        )
        with Session(self.engine) as session:
            return session.exec(stmt).first() is not None

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
        insert_stmt = sqlite_insert(ScrapeProgressRecord)
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=[
                ScrapeProgressRecord.category_id,
                ScrapeProgressRecord.brand_id,
                ScrapeProgressRecord.keyword,
            ],
            set_={
                "status": "completed",
                "total_rows": total_rows,
                "scraped_count": scraped_count,
                "updated_at": text("CURRENT_TIMESTAMP"),
            },
        )
        with self._tx() as session:
            session.execute(
                stmt,
                [
                    {
                        "category_id": category_id,
                        "brand_id": b_id,
                        "keyword": kw,
                        "status": "completed",
                        "total_rows": total_rows,
                        "scraped_count": scraped_count,
                    }
                ],
            )

    def record_seen_products(self, product_ids: Set[int]) -> None:
        """Record product IDs as seen during the current scrape pass."""
        if not product_ids:
            return
        stmt = sqlite_insert(ScrapedSeenProductRecord).on_conflict_do_nothing(
            index_elements=[ScrapedSeenProductRecord.product_id]
        )
        rows = [{"product_id": pid} for pid in product_ids]
        with self._tx() as session:
            session.execute(stmt, rows)

    def has_incomplete_progress(self) -> bool:
        """Check if there is active in-progress scrape data in progress tables."""
        if not self._has_table("scrape_progress"):
            return False
        stmt = select(func.count()).select_from(ScrapeProgressRecord)
        with Session(self.engine) as session:
            return session.execute(stmt).scalar() > 0

    def clear_scrape_progress(self) -> None:
        """Clear all scrape progress and seen products tables after a full scrape cycle finishes."""
        with self._tx() as session:
            session.execute(delete(ScrapeProgressRecord))
            session.execute(delete(ScrapedSeenProductRecord))

    def mark_unseen_stock_zero_from_db(self) -> int:
        """Mark products stock as 0 if they were not seen in the current multi-stage scrape run."""
        stmt = select(func.count()).select_from(ScrapedSeenProductRecord)
        with Session(self.engine) as session:
            seen_count = session.execute(stmt).scalar() or 0
        if seen_count == 0:
            return 0

        subq = select(ScrapedSeenProductRecord.product_id)
        update_stmt = (
            update(ProductRecord)
            .where(ProductRecord.product_id.notin_(subq))
            .values(stock=0, stock_sz=0, stock_js=0, stock_hk=0)
        )
        with self._tx() as session:
            result = session.execute(update_stmt)
            return result.rowcount or 0
