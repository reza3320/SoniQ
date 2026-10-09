"""
organizer.py — File renaming, CSV tracking, and playlist management.

Handles:
  - Naming files per convention: {Title} - {Artist(s)}.mp3
  - Updating CSV status for batch tracking
  - All operations are local (no bridge dependency)
"""

import csv
import os
import time
from pathlib import Path
from typing import Optional

from soniq.diagnostics import get as diag


def rename_file(filepath: str, template: str = "{title} - {artist}",
                artist: str = "", title: str = "") -> Optional[str]:
    """Rename a music file according to naming template.

    Template supports {artist} and {title} placeholders.
    Returns the new file path, or None on failure.
    """
    if not os.path.exists(filepath):
        diag().add_step("rename_file", "failed",
                        error_code="ERR_ORG_001",
                        error_message=f"File not found: {filepath}")
        return None

    directory = os.path.dirname(filepath)
    ext = os.path.splitext(filepath)[1]

    new_name = template.format(artist=artist or "Unknown",
                               title=title or "Unknown")
    new_name = "".join(c if c.isalnum() or c in " .-_()[],&" else "_"
                       for c in new_name).strip()
    if not new_name:
        new_name = f"{artist or 'Unknown'} - {title or 'Unknown'}"

    new_path = os.path.join(directory, f"{new_name}{ext}")

    if new_path == filepath:
        return filepath

    try:
        counter = 1
        base, ext = os.path.splitext(new_path)
        while os.path.exists(new_path):
            new_path = f"{base}_{counter}{ext}"
            counter += 1
        os.rename(filepath, new_path)
        diag().add_step("rename_file", "ok",
                        details={"from": os.path.basename(filepath),
                                 "to": os.path.basename(new_path)})
        return new_path
    except OSError as e:
        diag().add_step("rename_file", "failed",
                        error_code="ERR_ORG_001", error_message=str(e))
        return None


def organize_file(filepath: str, target_dir: str = "") -> Optional[str]:
    """Move a file to the target directory. If target_dir is empty, no-op."""
    if not target_dir:
        return filepath
    if not os.path.exists(filepath):
        return None
    os.makedirs(target_dir, exist_ok=True)
    dest = os.path.join(target_dir, os.path.basename(filepath))
    try:
        counter = 1
        base, ext = os.path.splitext(dest)
        while os.path.exists(dest):
            dest = f"{base}_{counter}{ext}"
            counter += 1
        os.rename(filepath, dest)
        return dest
    except OSError as e:
        diag().add_step("organize_file", "failed",
                        error_code="ERR_ORG_002", error_message=str(e))
        return None


# ── CSV Tracking ────────────────────────────────────────────────────────

CSV_FIELDS = ["artist", "title", "status", "date", "longitude", "latitude",
              "source", "quality", "filepath"]


def read_csv(csv_path: str) -> tuple[list[dict], list[str]]:
    """Read CSV file. Returns (rows, fieldnames)."""
    if not os.path.exists(csv_path):
        return [], CSV_FIELDS
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            fields = reader.fieldnames or CSV_FIELDS
        return rows, fields
    except Exception as e:
        diag().add_step("csv_read", "failed",
                        error_code="ERR_ORG_004", error_message=str(e))
        return [], CSV_FIELDS


def write_csv(csv_path: str, rows: list[dict], fieldnames: list[str] = None):
    """Write rows to CSV."""
    try:
        os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames or CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    except Exception as e:
        diag().add_step("csv_write", "failed",
                        error_code="ERR_ORG_005", error_message=str(e))


def mark_csv(csv_path: str, artist: str, title: str, status: str,
             source: str = "", quality: str = "", filepath: str = ""):
    """Update a single song's status in the CSV."""
    if not csv_path or not os.path.exists(csv_path):
        return
    rows, fields = read_csv(csv_path)
    updated = False
    for row in rows:
        if (row.get("artist", "").strip() == artist.strip()
                and row.get("title", "").strip() == title.strip()):
            row["status"] = status
            if source:
                row["source"] = source
            if quality:
                row["quality"] = quality
            if filepath:
                row["filepath"] = filepath
            updated = True
            break
    if not updated:
        rows.append({
            "artist": artist, "title": title, "status": status,
            "source": source, "quality": quality, "filepath": filepath,
            "date": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "longitude": "", "latitude": "",
        })
    write_csv(csv_path, rows, fields)
