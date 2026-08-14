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
