"""Tests for database variant generation and compression."""

import sqlite3
import tarfile
from pathlib import Path

import pytest
from sqlmodel import col, select

from lcsc_db.db import (
    LCSCDatabase,
    compress_file,
    create_fts_only_variant,
    generate_all_variants,
    generate_variant,
)
from lcsc_db.models import Product


@pytest.fixture
def sample_db(tmp_path: Path) -> Path:
    """Create a temporary SQLite database populated with sample products and categories."""
    from lcsc_db.models import Category

    db_path = tmp_path / "sample.sqlite3"
    with LCSCDatabase(db_path=str(db_path)) as db:
        db.init_schema()
        db.upsert_categories(
            [
                Category(category_id=1, name_en="Microcontrollers"),
                Category(category_id=2, name_en="Wireless Modules"),
            ]
        )
        products = [
            Product(
                lcsc_number="C12345",
                mfr_part_number="STM32F103C8T6",
                brand_name="STMicroelectronics",
                package="LQFP-48",
                description="ARM Cortex-M3 32-bit MCU 72MHz 64KB Flash",
                first_category_name="Microcontrollers",
                second_category_name="ARM",
                stock=5000,
                jlcpcb_stock=3000,
                jlcpcb_library_type="Basic",
                pdf_url="https://example.com/stm32.pdf",
            ),
            Product(
                lcsc_number="C67890",
                mfr_part_number="ESP32-WROOM-32D",
                brand_name="Espressif",
                package="SMD-38",
                description="Wi-Fi & Bluetooth MCU Module 240MHz",
                first_category_name="Wireless Modules",
                second_category_name="Bluetooth",
                stock=1200,
                jlcpcb_stock=800,
                jlcpcb_library_type="Preferred",
                pdf_url="https://example.com/esp32.pdf",
            ),
        ]
        db.upsert_products(products, include_raw_json=True)
    return db_path


def test_create_fts_only_variant(sample_db: Path, tmp_path: Path) -> None:
    output_db = tmp_path / "sample_fts_only.sqlite3"
    create_fts_only_variant(sample_db, output_db)

    assert output_db.exists()

    conn = sqlite3.connect(output_db)
    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table';"
            ).fetchall()
        ]
        assert "products" not in tables
        assert "categories" in tables
        assert "products_fts" in tables

        # Search query using trigram MATCH
        cursor = conn.execute(
            "SELECT lcsc_number, mfr_part_number, stock, jlcpcb_stock, jlcpcb_library_type, pdf_url "
            "FROM products_fts WHERE products_fts MATCH 'STM32';"
        )
        rows = cursor.fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "C12345"
        assert rows[0][1] == "STM32F103C8T6"
        assert rows[0][2] == "5000" or rows[0][2] == 5000
        assert rows[0][3] == "3000" or rows[0][3] == 3000
        assert rows[0][4] == "Basic"
        assert rows[0][5] == "https://example.com/stm32.pdf"

        # Query using UNINDEXED column filter and lookup
        cursor2 = conn.execute(
            "SELECT lcsc_number, description FROM products_fts WHERE lcsc_number = 'C67890';"
        )
        rows2 = cursor2.fetchall()
        assert len(rows2) == 1
        assert rows2[0][0] == "C67890"

        # Verify categories table contents
        cats = conn.execute("SELECT id, name_en FROM categories ORDER BY id;").fetchall()
        assert len(cats) == 2
        assert cats[0] == (1, "Microcontrollers")
    finally:
        conn.close()


def test_compress_and_generate_variant(sample_db: Path, tmp_path: Path) -> None:
    res = generate_variant(sample_db, "fts_only", compress=True)
    assert res["db_path"].exists()
    assert res["archive_path"] is not None
    assert res["archive_path"].exists()
    assert str(res["archive_path"]).endswith(".tar.xz")

    # Verify tar archive content
    with tarfile.open(res["archive_path"], "r:xz") as tar:
        names = tar.getnames()
        assert res["db_path"].name in names


def test_generate_all_variants(sample_db: Path, tmp_path: Path) -> None:
    results = generate_all_variants(
        sample_db,
        output_dir=tmp_path,
        selected_variants=["fts_only", "no_raw_json"],
        compress=False,
    )
    assert len(results) == 2
    assert (tmp_path / "sample_fts_only.sqlite3").exists()
    assert (tmp_path / "sample_no_raw_json.sqlite3").exists()
