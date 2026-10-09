"""Shared chat transcript — every message the CLI or the tray shows.

Stored as plain lines in ``~/.soniq/transcript.log``: reopening either
surface replays the recent conversation, and the two stay in sync.
"""
from __future__ import annotations

import sys
from pathlib import Path

MAX_LINES = 2000
TRIM_AT_BYTES = 400_000

_own_pending: list[str] = []


def take_own() -> list[str]:
    """Return (and clear) the lines this process wrote since last call."""
    items = list(_own_pending)
    _own_pending.clear()
    return items


def transcript_path() -> Path:
    return Path.home() / ".soniq" / "transcript.log"


def write_line(text: str) -> None:
    """Append one message line (blank lines and pure prompts skipped)."""
    text = text.rstrip("\r\n").split("\r")[-1]
    if not text.strip():
        return
    try:
        path = transcript_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(text + "\n")
        _own_pending.append(text)
        if len(_own_pending) > 400:
            del _own_pending[:-400]
        if path.stat().st_size > TRIM_AT_BYTES:
            lines = path.read_text(encoding="utf-8-sig",
                                   errors="replace").splitlines()
            path.write_text("\n".join(lines[-MAX_LINES:]) + "\n",
                            encoding="utf-8")
    except OSError:
        pass


def read_all() -> list[str]:
    """Return every transcript line (oldest first)."""
    try:
        text = transcript_path().read_text(encoding="utf-8-sig",
                                           errors="replace")
    except OSError:
        return []
    return [ln for ln in text.splitlines() if ln.strip()]


def read_tail(count: int = 25) -> list[str]:
    """Return the last ``count`` messages (oldest first)."""
    return read_all()[-count:]


class Tee:
    """stdout wrapper that mirrors complete lines into the transcript."""

    def __init__(self, stream):
        self.stream = stream
        self._buf = ""

    def write(self, text: str) -> int:
        self.stream.write(text)
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            write_line(line)
        return len(text)

    def flush(self) -> None:
        self.stream.flush()

    def clear_buffer(self) -> None:
        self._buf = ""

    def isatty(self) -> bool:
        return bool(getattr(self.stream, "isatty", lambda: False)())

    def fileno(self):
        return self.stream.fileno()

    def __getattr__(self, name):
        return getattr(self.stream, name)


def start_capture() -> None:
    """Mirror everything the CLI prints into the shared transcript."""
    if not isinstance(sys.stdout, Tee):
        sys.stdout = Tee(sys.stdout)


def clear_pending() -> None:
    """Drop any unfinished fragment (a bare prompt) from the buffer."""
    if isinstance(sys.stdout, Tee):
        sys.stdout.clear_buffer()
