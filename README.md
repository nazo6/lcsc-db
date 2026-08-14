# LCSC Product Database (`lcsc-db`)

Automated scraper and SQLite database builder for all LCSC electronics component data.

## Features

- **Complete & Lossless**: Stores all product attributes (LCSC C-number, MFR part number, brand, package, description, price ladders, stock breakdown, MOQ, SPQ, MSL, ECCN, URLs) plus raw API JSON in `raw_json` column.
- **Fast Full-Text Search**: Built-in SQLite `FTS5` virtual table indexing part numbers, brands, packages, and descriptions.
- **Smart Access Reduction (`--instock-only`)**: Cuts API traffic by ~70% by fetching active/in-stock parts and retaining historical parts in SQLite.
- **`uv` Package Management**: Initialized as a library using `uv init --lib`, managed with `uv`.
- **Automated GitHub Action**: Runs weekly to update the SQLite database and upload a `.tar.xz` release asset to GitHub Releases.

## Installation

Ensure you have [`uv`](https://github.com/astral-sh/uv) installed.

```bash
git clone https://github.com/nazo6/lcsc-db.git
cd lcsc-db
uv sync
```

## Usage

You can run the CLI script defined in `pyproject.toml` (`lcsc-db`):

```bash
# Run help to view all options
uv run lcsc-db --help

# Run a test/dry-run scrape for Category #51 (1 page only)
uv run lcsc-db --category-id 51 --max-pages 1 --compress

# Run full in-stock scrape with default 2.0s delay
uv run lcsc-db --instock-only --compress
```

### CLI Options

| Option | Default | Description |
| :--- | :--- | :--- |
| `--db-path` | `lcsc.sqlite3` | Output SQLite database file path |
| `--delay` | `2.0` | Delay in seconds between API requests |
| `--instock-only / --no-inststock-only` | `True` | Fetch in-stock parts only (saves ~70% API calls) |
| `--include-raw-json / --no-include-raw-json` | `True` | Write full raw API JSON to the `raw_json` column (otherwise kept `NULL`; column always exists) |
| `--enable-fts / --no-enable-fts` | `True` | Build SQLite `FTS5` full-text search index |
| `--category-id` | `None` | Scrape a single category ID |
| `--max-pages` | `None` | Limit max pages per category |
| `--compress / --no-compress` | `False` | Compress database to `.tar.xz` upon completion |
| `--verbose / --no-verbose` | `False` | Enable verbose DEBUG logging |

## Running Tests

Run unit & integration tests using `pytest`:

```bash
uv run pytest
```

## Database Schema

The schema is defined as [SQLModel](https://sqlmodel.tiangolo.com/) table models in
`src/lcsc_db/schema.py` and managed through [Alembic](https://alembic.sqlalchemy.org/)
migrations in `src/lcsc_db/migrations/`. `lcsc-db` automatically runs pending migrations
(`alembic upgrade head`) whenever the database is opened for scraping, so existing
databases are upgraded in place. The `raw_json` column is always present; it is simply
left `NULL` when `--no-raw-json` is used.

```sql
CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    lcsc_number TEXT UNIQUE NOT NULL,      -- e.g. C105872
    mfr_part_number TEXT NOT NULL,          -- e.g. RC0402FR-075K1L
    brand_name TEXT,                        -- e.g. YAGEO
    package TEXT,                           -- e.g. 0402
    description TEXT,                       -- e.g. 5.1kΩ...
    category_id INTEGER,
    stock INTEGER DEFAULT 0,
    stock_sz INTEGER DEFAULT 0,             -- Shenzhen stock
    stock_js INTEGER DEFAULT 0,             -- Jiangsu stock
    stock_hk INTEGER DEFAULT 0,             -- Hong Kong stock
    moq INTEGER DEFAULT 1,                  -- Minimum Order Quantity
    spq INTEGER DEFAULT 1,                  -- Packaging step quantity
    min_packet_number INTEGER,
    min_packet_unit TEXT,
    product_unit TEXT,
    product_arrange TEXT,
    price_ladder TEXT,                      -- JSON array
    pdf_url TEXT,
    image_url TEXT,
    product_images TEXT,                    -- JSON array of URLs
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
    raw_json TEXT                           -- Full raw API response JSON (NULL when disabled)
);

-- Full text search
CREATE VIRTUAL TABLE products_fts USING fts5(
    lcsc_number, mfr_part_number, brand_name, package, description,
    content='products', content_rowid='product_id'
);
```

### Working on schema changes

For future schema changes, update the models in `src/lcsc_db/schema.py`, then create a
migration and run the test suite:

```bash
# 1. Create a scratch database with the current schema
uv run lcsc-db --db-path /tmp/scratch.sqlite3 --category-id 51 --max-pages 1

# 2. Autogenerate a migration from the model changes (review the generated file)
uv run alembic -c src/lcsc_db/migrations/alembic.ini revision --autogenerate -m "describe change"
```

> **Note**: SQLite has limited `ALTER TABLE` support. For column/constraint changes that
> SQLite cannot apply in place, use `with op.batch_alter_table(...)` in the migration
> (enabled via `render_as_batch = True` in `alembic.ini`).

