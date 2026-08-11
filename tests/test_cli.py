"""Integration tests for CLI entrypoint."""

from click.testing import CliRunner

from lcsc_db.cli import main


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "LCSC Product Catalog Database Builder CLI" in result.output
    assert "--instock-only" in result.output
    assert "--include-raw-json" in result.output
    assert "--enable-fts" in result.output
    assert "--max-duration" in result.output
    assert "--resume" in result.output
    assert "--fresh" in result.output


def test_cli_dry_run(tmp_path):
    db_file = tmp_path / "cli_test.sqlite3"
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
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

    assert result.exit_code == 0
    assert "Successfully processed" in result.output
    assert db_file.exists()
    assert (tmp_path / "cli_test.sqlite3.tar.gz").exists()

