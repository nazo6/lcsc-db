"""Tests for release_manager script."""

from pathlib import Path

from lcsc_db.release import (
    build_release_notes,
    extract_metadata_from_notes,
    format_size,
    inspect_file_sizes,
)


def test_format_size():
    assert format_size(None) == "N/A"
    assert format_size(500) == "500 B"
    assert format_size(2048) == "2.00 KB"
    assert format_size(10 * 1024 * 1024) == "10.00 MB"
    assert format_size(2 * 1024 * 1024 * 1024) == "2.00 GB"


def test_inspect_file_sizes(tmp_path: Path):
    db = tmp_path / "lcsc_only.sqlite3"
    archive = tmp_path / "lcsc_only.sqlite3.tar.xz"

    db.write_bytes(b"x" * 1000)
    archive.write_bytes(b"y" * 200)

    db_key, meta, arch_p = inspect_file_sizes(db)
    assert db_key == "lcsc_only.sqlite3"
    assert meta["db_size_bytes"] == 1000
    assert meta["archive_size_bytes"] == 200
    assert meta["variant"] == "LCSC Only (Base DB)"
    assert arch_p == archive


def test_build_and_extract_metadata():
    assets_meta = {
        "lcsc_only.sqlite3": {
            "variant": "LCSC Only (Base DB)",
            "archive_name": "lcsc_only.sqlite3.tar.xz",
            "description": "LCSC catalog only",
            "db_size_bytes": 1024 * 1024 * 100,
            "archive_size_bytes": 1024 * 1024 * 20,
        },
        "lcsc_fts_only.sqlite3": {
            "variant": "FTS Search DB (Main)",
            "archive_name": "lcsc_fts_only.sqlite3.tar.xz",
            "description": "FTS search database",
            "db_size_bytes": 1024 * 1024 * 50,
            "archive_size_bytes": 1024 * 1024 * 10,
        },
    }

    notes = build_release_notes(assets_meta, "2026-08-14 00:00:00 UTC")
    assert "100.00 MB" in notes
    assert "20.00 MB" in notes
    assert "50.00 MB" in notes
    assert "10.00 MB" in notes
    assert "| **LCSC Only (Base DB)** | `lcsc_only.sqlite3.tar.xz` | 20.00 MB | 100.00 MB |" in notes
    assert "| **FTS Search DB (Main)** | `lcsc_fts_only.sqlite3.tar.xz` | 10.00 MB | 50.00 MB |" in notes

    extracted = extract_metadata_from_notes(notes)
    assert extracted["lcsc_only.sqlite3"]["db_size_bytes"] == 1024 * 1024 * 100
    assert extracted["lcsc_fts_only.sqlite3"]["archive_size_bytes"] == 1024 * 1024 * 10
