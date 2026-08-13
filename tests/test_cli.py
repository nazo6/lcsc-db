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
    assert (tmp_path / "cli_test.sqlite3.tar.gz").exists()
