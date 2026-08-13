"""Integration tests for CLI entrypoint."""

import pytest

from pydantic_settings import CliApp

from lcsc_db.cli import Settings


def test_cli_help(capsys):
    with pytest.raises(SystemExit):
        CliApp.run(Settings, cli_args=["--help"])
    out = capsys.readouterr().out
    assert "LCSC Product Catalog Database Builder CLI" in out
    assert "--instock-only" in out
    assert "--include-raw-json" in out
    assert "--enable-fts" in out
    assert "--max-duration" in out
    assert "--resume" in out
    assert "--fresh" in out


def test_cli_dry_run(tmp_path, capsys):
    db_file = tmp_path / "cli_test.sqlite3"
    CliApp.run(
        Settings,
        cli_args=[
            "--db-path",
            str(db_file),
            "--category-id",
            "51",
            "--max-pages",
            "1",
            "--delay",
            "0.1",
            "--max-duration",
            "60",
            "--compress",
        ],
    )

    out = capsys.readouterr().out
    assert "Successfully processed" in out
    assert db_file.exists()
    assert (tmp_path / "cli_test.sqlite3.tar.gz").exists()
