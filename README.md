# lcsc-db

## Pre-built Database Downloads

Pre-built SQLite databases compressed with `.tar.xz` are published weekly in
[GitHub Releases](https://github.com/nazo6/lcsc-db/releases/latest).

### Available Database Variants

| Database Variant | Archive File | Description |
| :--- | :--- | :--- |
| **FTS Search DB** *(Recommended / Main)* | `lcsc_fts_only.sqlite3.tar.xz` | High-performance standalone FTS5 search DB with all attributes (`UNINDEXED`) & categories. |
| **LCSC Only (FTS Search DB)** | `lcsc_only_fts_only.sqlite3.tar.xz` | Standalone FTS5 search DB for LCSC catalog only (with all attributes `UNINDEXED` & categories). |
| **JLCPCB Integrated** *(Base Relational DB)* | `lcsc.sqlite3.tar.xz` | Full LCSC catalog merged with JLCPCB stock & library types (relational tables, with `raw_json`). |
| **LCSC Only** *(Base Relational DB)* | `lcsc_only.sqlite3.tar.xz` | Full LCSC catalog with live stock, pricing tiers (relational tables, with `raw_json`). |

### How to Download & Extract

You can download the latest release archives directly from GitHub Releases or
using the GitHub CLI:

```bash
# Download the main FTS Search database archive
gh release download latest -p "lcsc_fts_only.sqlite3.tar.xz"

# Extract the SQLite database
tar -xf lcsc_fts_only.sqlite3.tar.xz
# The database file 'lcsc_fts_only.sqlite3' is now ready for use
```

---

## Database Schema & Queries

### 1. FTS Search Database (`lcsc_fts_only.sqlite3`)
Designed for ultra-fast part lookup and interactive search:
- **`products_fts`**: Self-contained SQLite `FTS5` virtual table with trigram tokenizer.
  - **Indexed Columns**: `lcsc_number`, `mfr_part_number`, `brand_name`, `package`, `description`, `first_category_name`, `second_category_name`, `third_category_name`
  - **UNINDEXED Columns**: `stock`, `stock_sz`/`stock_js`/`stock_hk`, `moq`, `spq`, `price_ladder`, `pdf_url`, `image_url`, `product_images`, `msl`, `eccn`, `url`, `is_rohs`, `is_hot`, `is_reel`, `reel_price`, `jlcpcb_stock`, `jlcpcb_price_ladder`, `jlcpcb_library_type`, `jlcpcb_extra`, `last_updated`, etc.
- **`categories`**: Category hierarchy (`id`, `parent_id`, `name_en`, `name_cn`, `code`).

### 2. Base Relational Database (`lcsc.sqlite3` / `lcsc_only.sqlite3`)
- **`products`**: Standard relational table with all structured columns plus full `raw_json` API responses.
- **`categories`**: Category hierarchy.
- **`product_params`**: Normalized product key-value technical parameters.

---

### Example Queries (`lcsc_fts_only.sqlite3`)

#### 1. Fast Full-Text Search (Direct on `products_fts`, no JOIN needed)

```sql
SELECT
    lcsc_number,
    mfr_part_number,
    brand_name,
    package,
    description,
    stock AS lcsc_stock,
    jlcpcb_stock,
    jlcpcb_library_type,
    pdf_url
FROM products_fts
WHERE products_fts MATCH 'stm32f401'
ORDER BY stock DESC
LIMIT 20;
```

#### 2. Find JLCPCB Basic / Preferred Components

```sql
SELECT
    lcsc_number,
    mfr_part_number,
    brand_name,
    package,
    description,
    jlcpcb_stock,
    jlcpcb_library_type
FROM products_fts
WHERE jlcpcb_library_type IN ('Basic', 'Preferred')
  AND jlcpcb_stock > 1000
ORDER BY jlcpcb_stock DESC
LIMIT 20;
```

#### 3. Exact Part Lookup by LCSC Part Number

```sql
SELECT
    lcsc_number,
    mfr_part_number,
    brand_name,
    package,
    description,
    stock,
    price_ladder,
    pdf_url
FROM products_fts
WHERE lcsc_number = 'C105872';
```

## CLI Usage (Building from Source)

If you want to build or update the databases yourself, install dependencies with
[`uv`](https://github.com/astral-sh/uv):

```bash
git clone https://github.com/nazo6/lcsc-db.git
cd lcsc-db
uv sync
```

## Running Tests

Run the test suite using `pytest`:

```bash
uv run pytest
```
