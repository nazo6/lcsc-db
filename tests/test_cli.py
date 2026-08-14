"""Integration tests for CLI entrypoint."""

import pytest

from lcsc_db.cli import build_parser, main


def test_cli_help(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["lcsc-db", "--help"])
    with pytest.raises(SystemExit):
        main()
    out = capsys.readouterr().out
    assert "sync-jlcpcb" in out
    assert "scrape-lcsc" in out
    assert "create-variants" in out
    assert "update-release" in out


def test_cli_create_variants_help(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["lcsc-db", "create-variants", "--help"])
    with pytest.raises(SystemExit):
        main()
    out = capsys.readouterr().out
    assert "--variants" in out
    assert "--compress" in out


def test_cli_update_release_help(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["lcsc-db", "update-release", "--help"])
    with pytest.raises(SystemExit):
        main()
    out = capsys.readouterr().out
    assert "--tag" in out
    assert "--files" in out
    assert "--dry-run" in out


def test_cli_sync_jlcpcb_help(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["lcsc-db", "sync-jlcpcb", "--help"])
    with pytest.raises(SystemExit):
        main()
    out = capsys.readouterr().out
    assert "--cache-dir" in out
    assert "--enable-fts" in out


def test_cli_scrape_dry_run(tmp_path, capsys, monkeypatch):
    db_file = tmp_path / "cli_test.sqlite3"
    monkeypatch.setattr(
        "sys.argv",
        [
            "lcsc-db",
            "scrape-lcsc",
            "--db-path",
            str(db_file),
            "--category-id",
            "51",
            "--max-pages",
            "1",
            "--delay",
            "0.1",
            "--compress",
        ],
    )
    main()

    out = capsys.readouterr().out
    assert "Successfully processed" in out
    assert db_file.exists()
    assert (tmp_path / "cli_test.sqlite3.tar.xz").exists()


def test_cli_create_variants_execution(tmp_path, capsys, monkeypatch):
    from lcsc_db.db import LCSCDatabase
    from lcsc_db.models import Product

    db_file = tmp_path / "base.sqlite3"
    with LCSCDatabase(db_path=str(db_file)) as db:
        db.init_schema(enable_fts=True)
        db.upsert_products(
            [
                Product(
                    lcsc_number="C1111",
                    mfr_part_number="TEST-MCU",
                    brand_name="BrandX",
                    description="Test MCU Description",
                )
            ]
        )

    monkeypatch.setattr(
        "sys.argv",
        [
            "lcsc-db",
            "create-variants",
            "--db-path",
            str(db_file),
            "--variants",
            "fts_only",
            "--compress",
        ],
    )
    main()

    assert (tmp_path / "base_fts_only.sqlite3").exists()
    assert (tmp_path / "base_fts_only.sqlite3.tar.xz").exists()


def test_cli_update_release_dry_run(tmp_path, capsys, monkeypatch):
    dummy_db = tmp_path / "lcsc_only.sqlite3"
    dummy_db.write_bytes(b"x" * 1024)
    dummy_archive = tmp_path / "lcsc_only.sqlite3.tar.xz"
    dummy_archive.write_bytes(b"y" * 512)

    monkeypatch.setattr(
        "sys.argv",
        [
            "lcsc-db",
            "update-release",
            "--files",
            str(dummy_db),
            "--dry-run",
        ],
    )
    main()

    out = capsys.readouterr().out
    assert "Generated Release Notes:" in out
    assert "1.00 KB" in out
    assert "512 B" in out
    assert "Dry-run enabled" in out


def test_compress_database_fast_and_fallback(tmp_path, monkeypatch):
    from lcsc_db.cli import compress_database
    import tarfile

    # 1. Test standard/fast path
    db_file1 = tmp_path / "sample1.sqlite3"
    db_file1.write_bytes(b"SQLite format 3\x00test content 12345")
    archive1 = compress_database(str(db_file1))
    assert (tmp_path / "sample1.sqlite3.tar.xz").exists()

    with tarfile.open(archive1, "r:xz") as tar:
        names = tar.getnames()
        assert "sample1.sqlite3" in names
        f = tar.extractfile("sample1.sqlite3")
        assert f is not None
        assert f.read() == b"SQLite format 3\x00test content 12345"

    # 2. Test fallback path (mocking shutil.which to return None)
    db_file2 = tmp_path / "sample2.sqlite3"
    db_file2.write_bytes(b"SQLite format 3\x00fallback test content")
    monkeypatch.setattr("shutil.which", lambda prog: None)

    archive2 = compress_database(str(db_file2))
    assert (tmp_path / "sample2.sqlite3.tar.xz").exists()

    with tarfile.open(archive2, "r:xz") as tar:
        names = tar.getnames()
        assert "sample2.sqlite3" in names
        f = tar.extractfile("sample2.sqlite3")
        assert f is not None
        assert f.read() == b"SQLite format 3\x00fallback test content"
