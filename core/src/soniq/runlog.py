"""
runlog.py — Human-readable run log.

Every run appends a plain-text log to ~/.soniq/logs/soniq.log — never
inside the app folder, so the installation stays clean. Logging must
never raise or crash the app.
"""

import time
from pathlib import Path
from typing import Optional

_resolved = False
_log_path: Optional[Path] = None


def _log_file() -> Optional[Path]:
    """Pick the log file location once: app folder first, home fallback."""
    global _resolved, _log_path
    if _resolved:
        return _log_path
    _resolved = True
    try:
        base = Path.home() / ".soniq" / "logs"
        base.mkdir(parents=True, exist_ok=True)
        path = base / "soniq.log"
        with open(path, "a", encoding="utf-8"):
            pass
        _log_path = path
        return path
    except OSError:
        return None


def log(message: str) -> None:
    """Append one timestamped line to the run log. Never raises."""
    try:
        path = _log_file()
        if not path:
            return
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {message}\n")
    except Exception:
        pass
