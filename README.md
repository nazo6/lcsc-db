# lcsc-db

## Pre-built Database Downloads

Pre-built SQLite databases compressed with `.tar.xz` are published weekly in
[GitHub Releases](https://github.com/nazo6/lcsc-db/releases/latest).

### Available Database Variants

| Database Variant | Archive File | Description |
| :--- | :--- | :--- |
| **JLCPCB Integrated** *(Default)* | `lcsc.sqlite3.tar.xz` | Full LCSC catalog merged with JLCPCB stock & library types, with FTS5 index. |
| **LCSC Only** | `lcsc_only.sqlite3.tar.xz` | Full LCSC catalog with live stock, pricing tiers, and FTS5 index. |
| **FTS Only** | `lcsc_fts_only.sqlite3.tar.xz` | Lightweight standalone FTS5 search index for fast part lookup. |

### How to Download & Extract

You can download the latest release archives directly from GitHub Releases or
using the GitHub CLI:

```bash
# Download the JLCPCB Integrated database archive
gh release download latest -p "lcsc.sqlite3.tar.xz"

# Extract the SQLite database
tar -xf lcsc.sqlite3.tar.xz
# The database file 'lcsc.sqlite3' is now ready for use
```

---

## Database Schema & Queries

The SQLite database consists of three main tables:

- **`products`**: Main component table storing all part details.
  - **Identifiers**: `lcsc_number` (Primary Key, e.g. `C105872`),
    `mfr_part_number`, `brand_name`, `package`
  - **Specs & Metadata**: `description`, `first_category_name`,
    `second_category_name`, `pdf_url` (datasheet), `image_url`
  - **Stock & Pricing**: `stock` (total LCSC stock),
    `stock_sz`/`stock_js`/`stock_hk` (warehouse breakdown), `price_ladder`
    (JSON), `moq`, `spq`
  - **JLCPCB Integration**: `jlcpcb_stock`, `jlcpcb_price_ladder`,
    `jlcpcb_library_type` (`Basic`, `Preferred`, `Extended`), `jlcpcb_extra`
  - **Raw Payload**: `raw_json` (Full LCSC API response)
- **`categories`**: Category hierarchy (`id`, `parent_id`, `name_en`).
- **`products_fts`**: SQLite `FTS5` virtual table with trigram tokenizer for
  ultra-fast substring and keyword search.

### Example Queries

#### 1. Fast Full-Text Search (FTS5 Trigram)

```sql
SELECT
    p.lcsc_number,
    p.mfr_part_number,
    p.brand_name,
    p.package,
    p.description,
    p.stock AS lcsc_stock,
    p.jlcpcb_stock,
    p.jlcpcb_library_type
FROM products p
JOIN products_fts fts ON fts.rowid = p.rowid
WHERE products_fts MATCH 'stm32f401'
ORDER BY p.stock DESC
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
FROM products
WHERE jlcpcb_library_type IN ('Basic', 'Preferred')
  AND jlcpcb_stock > 1000
ORDER BY jlcpcb_stock DESC
LIMIT 20;
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
