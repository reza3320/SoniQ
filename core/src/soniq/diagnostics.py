"""
diagnostics.py — Error tracking and run reporting.

Every component in this application reports its progress and any failures
through this module. After each run a JSON report is saved so you can
see exactly which songs succeeded, which failed, and why.

Error codes follow a pattern: ERR_<MODULE>_<NUMBER>
  ERR_NET_*    = network / connection issues
  ERR_SRC_*   = source-specific failures (search, scrape, download)
  ERR_META_*  = metadata processing failures
  ERR_ORG_*   = file organization / renaming failures
  ERR_CFG_*   = configuration issues
  ERR_GEN_*   = anything that does not fit above
"""

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from soniq.runlog import log as runlog


# -- Error Code Reference ----------------------------------------------------
# Each code maps to a human-readable explanation. When a user sees
# ERR_NET_001 in their diagnostics file, they know exactly what it means.

ERROR_CODES = {
    # Network layer
    "ERR_NET_001": "Could not reach the download service (connection timeout)",
    "ERR_NET_002": "Download service returned an unexpected response",
    "ERR_NET_003": "Service appears to be offline or blocked in your region",
    "ERR_NET_004": "DNS resolution failed — check your internet connection",

    # Source providers
    "ERR_SRC_001": "No results found for this song",
    "ERR_SRC_002": "Found the song but no suitable quality was available",
    "ERR_SRC_003": "Download page could not be loaded",
    "ERR_SRC_004": "Download link was missing or expired",
    "ERR_SRC_005": "File download failed — connection interrupted",
    "ERR_SRC_006": "Downloaded file is empty or corrupted",
    "ERR_SRC_007": "All sources exhausted — song not found anywhere",
    "ERR_SRC_008": "Source provider is temporarily unavailable (try again later)",

    # YouTube / external tools
    "ERR_YT_001": "External downloader (yt-dlp) is not installed or not found",
    "ERR_YT_002": "No results found on secondary source",
    "ERR_YT_003": "External downloader encountered an error",
    "ERR_YT_004": "Could not determine audio quality for this track",
    "ERR_YT_005": "Downloaded file could not be located after processing",
    "ERR_YT_006": "No acceptable audio candidate found on the secondary source",
    "ERR_YT_007": "No search result matched the song (music videos, live versions, remixes and covers are filtered out)",

    # Metadata processing
    "ERR_META_001": "Metadata service request failed",
    "ERR_META_002": "File not found when attempting to write metadata",
    "ERR_META_003": "Could not write metadata tags (file may be locked or unsupported)",
    "ERR_META_004": "Unsupported file format for metadata processing",

    # File organization
    "ERR_ORG_001": "Failed to rename downloaded file",
    "ERR_ORG_002": "Failed to move file to target directory",
    "ERR_ORG_003": "Failed to write tracking information",

    # Configuration
    "ERR_CFG_001": "Configuration file is missing or unreadable",
    "ERR_CFG_002": "Invalid configuration value",

    # General
    "ERR_GEN_001": "An unexpected error occurred",
    "ERR_GEN_002": "Operation timed out",
}


# -- Step Log Entry ----------------------------------------------------------
# Each song goes through several steps (search, decide, download, metadata).
# Steps are logged individually so failures can be pinpointed.

@dataclass
class Step:
    name: str                    # Name of the step, e.g. "source_search"
    status: str                  # "ok" | "skipped" | "failed"
    duration_ms: float = 0.0     # How long this step took
    error_code: str = ""         # Error code if failed
    error_message: str = ""      # Human-readable error if failed
    details: dict = field(default_factory=dict)  # Extra context


# -- Per-Song Result ---------------------------------------------------------
# When processing finishes (success or failure), the result is stored here.

@dataclass
class SongResult:
    artist: str
    title: str
    status: str                  # "pending" | "success" | "failed" | "skipped"
    quality: str = ""            # e.g. "320", "256", "192"
    filepath: str = ""
    metadata: dict = field(default_factory=dict)
    steps: list = field(default_factory=list)
    error_code: str = ""
    error_message: str = ""


# -- Environment Snapshot ----------------------------------------------------
# Versions captured once per run; included in every report so failures can
# be matched against tool versions (especially yt-dlp, which changes often).

def _environment() -> dict:
    """Collect app / Python / yt-dlp versions for the report header."""
    import platform
    env = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "soniq": "",
        "yt_dlp": "",
    }
    try:
        from soniq import __version__ as soniq_version
        env["soniq"] = soniq_version
    except Exception:
        pass
    try:
        result = subprocess.run(["yt-dlp", "--version"],
                                capture_output=True, text=True, timeout=5)
        env["yt_dlp"] = (result.stdout or result.stderr or "").strip()[:40]
    except Exception:
        env["yt_dlp"] = "not found"
    return env


# -- Diagnostics Collector ---------------------------------------------------
# Collects results across all songs and writes a final JSON report.

class Diagnostics:
    """
    Tracks what happens to every song during a run.

    Usage:
        from diagnostics import get as diag
        diag().begin_song("Artist", "Title")
        diag().add_step("search", "ok")
        diag().end_song("success")
        report = diag().to_json("path/to/report.json")
    """

    def __init__(self):
        self.run_id = time.strftime("%Y-%m-%d_%H:%M:%S")
        self.start_time = time.time()
        self.env = _environment()
        runlog(f"RUN START | soniq {self.env.get('soniq', '?')} | "
               f"yt-dlp {self.env.get('yt_dlp', '?')} | "
               f"python {self.env.get('python', '?')}")
        self.songs: list[SongResult] = []
        self._current: Optional[SongResult] = None

    @property
    def filename_id(self) -> str:
        """Run id made safe for file names on every platform.

        Windows forbids ':' in file names; report files are named
        after this id (the display run_id is untouched).
        """
        return self.run_id.replace(":", "-")

    def begin_song(self, artist: str, title: str):
        """Start tracking a new song. Call this before processing."""
        self._current = SongResult(artist=artist, title=title, status="pending")
        self.songs.append(self._current)
        runlog(f"START  {artist} - {title}")

    def add_step(self, name: str, status: str, details: dict = None,
                 error_code: str = "", error_message: str = "",
                 duration_ms: float = 0.0):
        """Record one step within the current song's pipeline."""
        if self._current is None:
            return
        step = Step(
            name=name, status=status,
            error_code=error_code, error_message=error_message,
            details=details or {}, duration_ms=duration_ms
        )
        self._current.steps.append(step)
        if status == "failed":
            runlog(f"  STEP FAILED  {name} [{error_code or '-'}] "
                   f"{(error_message or '')[:160]}")

    def end_song(self, status: str, quality: str = "",
                 filepath: str = "", metadata: dict = None,
                 error_code: str = "", error_message: str = ""):
        """Finish tracking the current song with its final result."""
        if self._current is None:
            return
        self._current.status = status
        self._current.quality = quality
        self._current.filepath = filepath
        self._current.metadata = metadata or {}
        self._current.error_code = error_code
        self._current.error_message = error_message
        if status == "success":
            runlog(f"  RESULT ok [{quality}] {filepath}")
        else:
            runlog(f"  RESULT {status} [{error_code or '-'}] "
                   f"{(error_message or '')[:160]}")
        self._current = None

    def fail(self, error_code: str, error_message: str = ""):
        """Quick-fail the current song without additional steps."""
        msg = error_message or ERROR_CODES.get(error_code, "Unknown error")
        self.add_step("failure", "failed",
                      error_code=error_code, error_message=msg)
        if self._current:
            self._current.status = "failed"
            self._current.error_code = error_code
            self._current.error_message = msg
            runlog(f"  RESULT failed [{error_code}] {msg[:160]}")

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time

    def summary(self) -> dict:
        """Aggregate stats: how many succeeded, failed, by quality, etc."""
        total = len(self.songs)
        success = sum(1 for s in self.songs if s.status == "success")
        failed = sum(1 for s in self.songs if s.status == "failed")
        skipped = sum(1 for s in self.songs if s.status == "skipped")

        quality_counts = {}
        for s in self.songs:
            if s.quality:
                quality_counts[s.quality] = quality_counts.get(s.quality, 0) + 1

        return {
            "run_id": self.run_id,
            "total": total,
            "success": success,
            "failed": failed,
            "skipped": skipped,
            "quality_breakdown": quality_counts,
            "total_duration_seconds": round(self.elapsed_seconds, 1),
        }

    def to_json(self, path: str = ""):
        """Export the full run report to a JSON file.
        If path is empty, returns the dict without saving.
        """
        report = {
            "run_id": self.run_id,
            "environment": self.env,
            "total": len(self.songs),
            "success": sum(1 for s in self.songs if s.status == "success"),
            "failed": sum(1 for s in self.songs if s.status == "failed"),
            "skipped": sum(1 for s in self.songs if s.status == "skipped"),
            "songs": [asdict(s) for s in self.songs],
            "summary": self.summary(),
        }
        if path:
            # Saving a report must never crash the application — any
            # failure (permissions, invalid path, locked file, or an
            # unserializable object) is swallowed. default=str keeps
            # stray objects from killing the dump.
            try:
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(report, f, indent=2, ensure_ascii=False,
                              default=str)
            except Exception:
                pass
        return report

    def print_failures(self):
        """Print a compact failure list to stderr (useful for CLI display)."""
        failed = [s for s in self.songs if s.status == "failed"]
        if not failed:
            return
        print("\nFailures:", file=sys.stderr)
        for s in failed:
            code = s.error_code or "?"
            msg = s.error_message or "No details provided"
            print(f"  [{code}] {s.artist} - {s.title}: {msg}", file=sys.stderr)


# -- Singleton ---------------------------------------------------------------
# A single Diagnostics instance is reused throughout the application.
# Call get() from any module to access it.

_diagnostics: Optional[Diagnostics] = None


def get() -> Diagnostics:
    """Return the shared Diagnostics instance. Creates one if needed."""
    global _diagnostics
    if _diagnostics is None:
        _diagnostics = Diagnostics()
    return _diagnostics
