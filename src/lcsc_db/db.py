"""SQLite Database Manager for LCSC product catalog."""

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Set

from alembic import command
from alembic.config import Config
from sqlalchemy import delete, func, inspect, text, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session, col, create_engine, select

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
        update_cols = [c for c in CategoryRecord.model_fields if c != "id"]
        insert_stmt = sqlite_insert(CategoryRecord)
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=[col(CategoryRecord.id)],
            set_={c: getattr(insert_stmt.excluded, c) for c in update_cols},
        )
        rows = [CategoryRecord.from_category(cat) for cat in categories_list]
        with self._tx() as session:
            if rows:
                session.exec(stmt, params=[r.model_dump() for r in rows])

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
            c
            for c in ProductRecord.model_fields
            if c not in ("product_id", "last_updated", "raw_json")
        ]
        if include_raw_json:
            update_cols.append("raw_json")

        insert_stmt = sqlite_insert(ProductRecord)
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=[col(ProductRecord.product_id)],
            set_={
                **{c: getattr(insert_stmt.excluded, c) for c in update_cols},
                "last_updated": text("CURRENT_TIMESTAMP"),
            },
        )

        product_records = []
        param_rows = []

        for p in products:
            record = ProductRecord.from_product(p, include_raw_json=include_raw_json)
            if record is None:
                continue
            product_records.append(record)

            for param in p.params or []:
                if param.name and param.value:
                    param_rows.append(
                        {
                            "product_id": record.product_id,
                            "param_name": param.name,
                            "param_value": param.value,
                        }
                    )

        with self._tx() as session:
            if product_records:
                session.exec(stmt, params=[r.model_dump() for r in product_records])

                # Refresh parameters for inserted products
                pids = [r.product_id for r in product_records]
                session.exec(
                    delete(ProductParamRecord).where(
                        col(ProductParamRecord.product_id).in_(pids)
                    )
                )
                if param_rows:
                    session.exec(sqlite_insert(ProductParamRecord), params=param_rows)

    def rebuild_fts(self) -> None:
        """Rebuild FTS5 index for full-text search."""
        if not self._has_table("products_fts"):
            return
        with self._tx() as session:
            session.connection().execute(
                text("INSERT INTO products_fts(products_fts) VALUES('rebuild');")
            )

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
            col(ScrapeProgressRecord.category_id) == category_id,
            col(ScrapeProgressRecord.brand_id) == b_id,
            col(ScrapeProgressRecord.keyword) == kw,
            col(ScrapeProgressRecord.status) == "completed",
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
                col(ScrapeProgressRecord.category_id),
                col(ScrapeProgressRecord.brand_id),
                col(ScrapeProgressRecord.keyword),
            ],
            set_={
                "status": "completed",
                "total_rows": total_rows,
                "scraped_count": scraped_count,
                "updated_at": text("CURRENT_TIMESTAMP"),
            },
        )
        with self._tx() as session:
            session.exec(
                stmt,
                params=[
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
            index_elements=[col(ScrapedSeenProductRecord.product_id)]
        )
        rows = [{"product_id": pid} for pid in product_ids]
        with self._tx() as session:
            session.exec(stmt, params=rows)

    def has_incomplete_progress(self) -> bool:
        """Check if there is active in-progress scrape data in progress tables."""
        if not self._has_table("scrape_progress"):
            return False
        stmt = select(func.count()).select_from(ScrapeProgressRecord)
        with Session(self.engine) as session:
            return session.exec(stmt).one() > 0

    def clear_scrape_progress(self) -> None:
        """Clear all scrape progress and seen products tables after a full scrape cycle finishes."""
        with self._tx() as session:
            session.exec(delete(ScrapeProgressRecord))
            session.exec(delete(ScrapedSeenProductRecord))

    def mark_unseen_stock_zero_from_db(self) -> int:
        """Mark products stock as 0 if they were not seen in the current multi-stage scrape run."""
        stmt = select(func.count()).select_from(ScrapedSeenProductRecord)
        with Session(self.engine) as session:
            seen_count = session.exec(stmt).one() or 0
        if seen_count == 0:
            return 0

        subq = select(col(ScrapedSeenProductRecord.product_id))
        update_stmt = (
            update(ProductRecord)
            .where(col(ProductRecord.product_id).notin_(subq))
            .values(stock=0, stock_sz=0, stock_js=0, stock_hk=0)
        )
        with self._tx() as session:
            result = session.exec(update_stmt)
            return result.rowcount or 0
