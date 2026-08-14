"""Benchmark and measure size differences for SQLite database variants.

Measures full DB baseline, No FTS, No raw_json, and Minimal variants by executing SQL transformations on temporary copies.
"""

import argparse
import os
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
from pathlib import Path


def compress_file(file_path: Path) -> Path:
    """Compress a file to .tar.xz and return the archive path using xz/tar if available."""
    archive_path = file_path.with_suffix(file_path.suffix + ".tar.xz")
    compressed_fast = False
    if shutil.which("tar") is not None and shutil.which("xz") is not None:
        try:
            cmd = ["tar", "-I", "xz -T0", "-cf", str(archive_path.resolve()), file_path.name]
            subprocess.run(cmd, cwd=str(file_path.parent), check=True, capture_output=True)
            compressed_fast = True
        except Exception:
            compressed_fast = False

    if not compressed_fast:
        with tarfile.open(archive_path, "w:xz") as tar:
            tar.add(file_path, arcname=file_path.name)
    return archive_path


from lcsc_db.variants import create_fts_only_variant


def measure_variant(
    base_db_path: Path,
    variant_name: str,
    sql_commands: list[str] | None = None,
) -> dict:
    """Create a temporary copy of base_db_path, apply SQL commands, and measure sizes."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_db = Path(tmp_dir) / f"work_{variant_name}.sqlite3"
        shutil.copy2(base_db_path, tmp_db)

        if sql_commands:
            conn = sqlite3.connect(tmp_db, isolation_level=None)
            try:
                for sql in sql_commands:
                    conn.execute(sql)
            finally:
                conn.close()

        archive_path = compress_file(tmp_db)

        db_bytes = tmp_db.stat().st_size
        xz_bytes = archive_path.stat().st_size

        return {
            "variant": variant_name,
            "db_size_mb": db_bytes / (1024 * 1024),
            "xz_size_mb": xz_bytes / (1024 * 1024),
        }


def measure_fts_variant(base_db_path: Path) -> dict:
    """Create standalone FTS variant and measure sizes."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_db = Path(tmp_dir) / "work_fts_only.sqlite3"
        create_fts_only_variant(base_db_path, tmp_db)
        archive_path = compress_file(tmp_db)

        db_bytes = tmp_db.stat().st_size
        xz_bytes = archive_path.stat().st_size

        return {
            "variant": "FTS Search DB (Main / Standalone FTS5)",
            "db_size_mb": db_bytes / (1024 * 1024),
            "xz_size_mb": xz_bytes / (1024 * 1024),
        }


def run_benchmark(db_path: Path, label: str, output_markdown: Path | None = None) -> str:
    """Run benchmark across variants and generate a markdown table."""
    if not db_path.exists():
        raise FileNotFoundError(f"Database file not found: {db_path}")

    print(f"Benchmarking variants for: {label} ({db_path})")

    # 1. Base DB (relational, with raw_json, no FTS)
    base = measure_variant(db_path, "Base DB (Relational, raw_json: Yes, FTS: No)")

    # 2. Standalone FTS variant
    fts = measure_fts_variant(db_path)

    # 3. No raw_json
    no_raw = measure_variant(
        db_path,
        "No raw_json (Relational, raw_json: No)",
        ["UPDATE products SET raw_json = NULL;", "VACUUM;"],
    )

    results = [base, fts, no_raw]

    base_db_mb = base["db_size_mb"]
    base_xz_mb = base["xz_size_mb"]

    lines = [
        f"### Size Benchmark Report: {label}",
        "",
        "| Variant | DB Size (MB) | Savings | Archive (.tar.xz) | Archive Savings |",
        "| :--- | :---: | :---: | :---: | :---: |",
    ]

    for r in results:
        db_mb = r["db_size_mb"]
        xz_mb = r["xz_size_mb"]

        db_diff = ((db_mb - base_db_mb) / base_db_mb) * 100 if base_db_mb > 0 else 0
        xz_diff = ((xz_mb - base_xz_mb) / base_xz_mb) * 100 if base_xz_mb > 0 else 0

        db_diff_str = "Baseline" if r == base else f"{db_diff:+.1f}%"
        xz_diff_str = "Baseline" if r == base else f"{xz_diff:+.1f}%"

        lines.append(
            f"| **{r['variant']}** | {db_mb:.2f} MB | {db_diff_str} | {xz_mb:.2f} MB | {xz_diff_str} |"
        )

    lines.append("")
    report = "\n".join(lines)
    print(report)

    if output_markdown:
        output_markdown.parent.mkdir(parents=True, exist_ok=True)
        with open(output_markdown, "a", encoding="utf-8") as f:
            f.write(report + "\n")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark SQLite DB variants size.")
    parser.add_argument("--db-path", required=True, type=Path, help="Input SQLite database file")
    parser.add_argument("--label", required=True, type=str, help="Dataset label (e.g. 'DB 2 (LCSC Only)')")
    parser.add_argument("--output-markdown", type=Path, default=None, help="Append markdown report to file")

    args = parser.parse_args()
    run_benchmark(args.db_path, args.label, args.output_markdown)


if __name__ == "__main__":
    main()
