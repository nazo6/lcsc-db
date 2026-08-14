"""Manage GitHub Releases and update release notes with file size statistics."""

import argparse
import datetime
import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

METADATA_COMMENT_PATTERN = re.compile(r"<!-- METADATA:\s*(\{.*?\})\s*-->", re.DOTALL)

KNOWN_ASSETS_META: dict[str, dict[str, Any]] = {
    "lcsc_fts_only.sqlite3": {
        "variant": "FTS Search DB (Main)",
        "archive_name": "lcsc_fts_only.sqlite3.tar.xz",
        "description": "Standalone FTS5 search DB with all attributes (UNINDEXED) & categories",
    },
    "lcsc_only_fts_only.sqlite3": {
        "variant": "LCSC Only (FTS Search DB)",
        "archive_name": "lcsc_only_fts_only.sqlite3.tar.xz",
        "description": "Standalone FTS5 search DB for LCSC catalog only",
    },
    "lcsc.sqlite3": {
        "variant": "JLCPCB Integrated (Base DB)",
        "archive_name": "lcsc.sqlite3.tar.xz",
        "description": "Full JLCPCB + LCSC relational database (with raw_json)",
    },
    "lcsc_only.sqlite3": {
        "variant": "LCSC Only (Base DB)",
        "archive_name": "lcsc_only.sqlite3.tar.xz",
        "description": "LCSC catalog only relational database (with raw_json)",
    },
    "lcsc_no_raw_json.sqlite3": {
        "variant": "No raw_json",
        "archive_name": "lcsc_no_raw_json.sqlite3.tar.xz",
        "description": "Full relational database (raw_json cleared)",
    },
    "lcsc_minimal.sqlite3": {
        "variant": "Minimal",
        "archive_name": "lcsc_minimal.sqlite3.tar.xz",
        "description": "Minimal relational database (raw_json cleared)",
    },
}


def format_size(size_bytes: int | None) -> str:
    """Format byte size into human-readable string."""
    if size_bytes is None:
        return "N/A"
    if size_bytes >= 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
    elif size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes} B"


def extract_metadata_from_notes(notes: str) -> dict[str, Any]:
    """Extract metadata JSON embedded in release notes."""
    match = METADATA_COMMENT_PATTERN.search(notes)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass
    return {}


def build_release_notes(assets_meta: dict[str, dict[str, Any]], updated_at_str: str) -> str:
    """Generate Markdown release notes including file size statistics."""
    lines = [
        "Automated LCSC Product Database build release.",
        "",
        "### Available Database Files & Sizes:",
        "| Database Variant | Archive File (.tar.xz) | Archive Size | DB Size (Uncompressed) | Description |",
        "| :--- | :--- | :---: | :---: | :--- |",
    ]

    # Sort items based on standard order if possible
    order = [
        "lcsc_fts_only.sqlite3",
        "lcsc_only_fts_only.sqlite3",
        "lcsc.sqlite3",
        "lcsc_only.sqlite3",
        "lcsc_no_raw_json.sqlite3",
        "lcsc_minimal.sqlite3",
    ]
    sorted_keys = sorted(
        assets_meta.keys(),
        key=lambda k: order.index(k) if k in order else 999,
    )

    for db_name in sorted_keys:
        info = assets_meta[db_name]
        variant = info.get("variant", db_name)
        archive_name = info.get("archive_name", f"{db_name}.tar.xz")
        archive_size = format_size(info.get("archive_size_bytes"))
        db_size = format_size(info.get("db_size_bytes"))
        desc = info.get("description", "")
        lines.append(
            f"| **{variant}** | `{archive_name}` | {archive_size} | {db_size} | {desc} |"
        )

    lines.append("")
    lines.append(f"*Last updated: {updated_at_str}*")
    lines.append("")
    # Embed JSON metadata for subsequent updates
    lines.append(f"<!-- METADATA: {json.dumps(assets_meta)} -->")

    return "\n".join(lines)


def inspect_file_sizes(file_path: Path) -> tuple[str, dict[str, Any], Path]:
    """Inspect uncompressed db size and compressed archive size for a given path.

    Returns (db_key, metadata_dict, archive_path).
    """
    path_str = file_path.name
    if path_str.endswith(".tar.xz"):
        db_stem = path_str[:-7]
        archive_path = file_path
        db_path = file_path.parent / db_stem
    else:
        db_stem = path_str
        db_path = file_path
        archive_path = file_path.parent / f"{path_str}.tar.xz"

    db_size = db_path.stat().st_size if db_path.exists() else None
    archive_size = archive_path.stat().st_size if archive_path.exists() else None

    meta = KNOWN_ASSETS_META.get(
        db_stem,
        {
            "variant": db_stem,
            "archive_name": archive_path.name,
            "description": "Database variant",
        },
    ).copy()

    meta["db_size_bytes"] = db_size
    meta["archive_size_bytes"] = archive_size
    meta["last_updated"] = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )

    return db_stem, meta, archive_path


def run_release_manager(
    tag: str,
    title: str,
    target_files: list[Path],
    dry_run: bool = False,
) -> None:
    """Upload files to GitHub release and update release notes with size stats."""
    existing_notes = ""
    release_exists = False

    try:
        res = subprocess.run(
            ["gh", "release", "view", tag, "--json", "body", "-q", ".body"],
            capture_output=True,
            text=True,
            check=True,
        )
        existing_notes = res.stdout
        release_exists = True
    except Exception:
        release_exists = False

    metadata = extract_metadata_from_notes(existing_notes)

    upload_archives: list[Path] = []
    for file_path in target_files:
        if not file_path.exists():
            print(f"Warning: file {file_path} does not exist. Skipping.")
            continue
        db_key, meta, archive_path = inspect_file_sizes(file_path)
        metadata[db_key] = meta
        if archive_path.exists() and archive_path not in upload_archives:
            upload_archives.append(archive_path)

    now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    new_notes = build_release_notes(metadata, now_str)

    print("==================================================")
    print("Generated Release Notes:")
    print(new_notes)
    print("==================================================")

    if dry_run:
        print("Dry-run enabled. Skipping GitHub Release upload.")
        return

    if not upload_archives:
        print("No archives found to upload.")
        return

    archive_str_paths = [str(p) for p in upload_archives]

    if not release_exists:
        print(f"Creating release '{tag}' with title '{title}'...")
        cmd = [
            "gh",
            "release",
            "create",
            tag,
            "--title",
            title,
            "--notes",
            new_notes,
            "--make-latest=true",
        ] + archive_str_paths
        subprocess.run(cmd, check=True)
    else:
        print(f"Uploading {len(archive_str_paths)} archive(s) to release '{tag}'...")
        upload_cmd = ["gh", "release", "upload", tag, "--clobber"] + archive_str_paths
        subprocess.run(upload_cmd, check=True)

        print(f"Updating release notes for '{tag}'...")
        edit_cmd = ["gh", "release", "edit", tag, "--notes", new_notes]
        subprocess.run(edit_cmd, check=True)

    print("Release successfully updated.")
