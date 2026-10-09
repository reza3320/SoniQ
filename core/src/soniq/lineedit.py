"""Shared command history + a small dependency-free line editor.

The history file (~/.soniq/history.txt) is shared with the tray window
(tray.ps1): both surfaces append every command and read it back, so
up/down in the CLI recalls commands typed in either place.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

MAX_LINES = 500
TRIM_AT = 700


def history_path() -> Path:
    return Path.home() / ".soniq" / "history.txt"


def load_history(limit: int = MAX_LINES) -> list[str]:
    """Return the most recent ``limit`` entries (oldest first)."""
    try:
        text = history_path().read_text(encoding="utf-8-sig",
                                        errors="replace")
    except OSError:
        return []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines[-limit:]


def append_history(command: str) -> None:
    """Append one command, skipping a consecutive duplicate."""
    command = command.strip()
    if not command:
        return
    path = history_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            lines = [ln for ln in text.splitlines() if ln.strip()]
        except OSError:
            pass
        if lines and lines[-1].strip() == command:
            return
        with path.open("a", encoding="utf-8") as fh:
            fh.write(command + "\n")
        if len(lines) + 1 > TRIM_AT:
            tail = (lines + [command])[-MAX_LINES:]
            path.write_text("\n".join(tail) + "\n", encoding="utf-8")
    except OSError:
        pass


def _edit_line_from_keys(read_key, prompt: str, history: list[str],
                         write) -> str:
    """Core editor loop over an abstract key source (unit-testable).

    Keys are single chars; ``\\r``/``\\n`` finish the line, ``\\x08`` is
    backspace, ``UP``/``DOWN`` recall history, ``\\x03`` raises
    KeyboardInterrupt (Ctrl+C).
    """
    buf = ""
    idx = len(history)
    with _live_lock:
        _live.update(active=True, prompt=prompt, buf="", drawn=0)
    try:
        write(prompt)
        while True:
            key = read_key()
            if key is None:
                raise EOFError
            if key in ("\r", "\n"):
                write("\n")
                return buf
            if key == "\x08":
                if buf:
                    buf = buf[:-1]
            elif key == "UP":
                if history and idx > 0:
                    idx -= 1
                    buf = history[idx]
            elif key == "DOWN":
                if idx < len(history) - 1:
                    idx += 1
                    buf = history[idx]
                else:
                    idx = len(history)
                    buf = ""
            elif key == "\x03":
                raise KeyboardInterrupt
            elif key == "\x1a":
                continue
            elif len(key) == 1 and key >= " ":
                buf += key
            else:
                continue
            with _live_lock:
                pad = max(0, _live["drawn"] - len(buf))
                write("\r" + prompt + buf + " " * pad)
                _live["buf"] = buf
                _live["drawn"] = len(buf)
    finally:
        with _live_lock:
            _live.update(active=False, buf="", drawn=0)


def _read_key_windows():
    """Read one key from the Windows console (arrow keys -> UP/DOWN)."""
    import msvcrt

    ch = msvcrt.getwch()
    if ch in ("\x00", "\xe0"):
        second = msvcrt.getwch()
        return {"H": "UP", "P": "DOWN"}.get(second, "")
    return ch


_live_lock = threading.Lock()
_live = {"active": False, "prompt": "", "buf": "", "drawn": 0,
         "thread": None, "seen": 0, "init": False}


def _live_print(text: str) -> None:
    """Show a line from the other surface without breaking the input."""
    out = getattr(sys.stdout, "stream", sys.stdout)
    with _live_lock:
        if _live["active"]:
            width = len(_live["prompt"]) + len(_live["buf"]) + 4
            out.write("\r" + " " * width + "\r")
        out.write(text + "\n")
        if _live["active"]:
            out.write(_live["prompt"] + _live["buf"])
            _live["drawn"] = len(_live["buf"])
        out.flush()


def _filter_own(new_lines: list[str], own: list[str]) -> list[str]:
    """Drop lines this process wrote itself (kept in write order)."""
    out = []
    for line in new_lines:
        if own and line == own[0]:
            own.pop(0)
            continue
        out.append(line)
    return out


def start_transcript_monitor(interval: float = 1.5) -> None:
    """Watch the shared transcript and surface new tray lines live."""
    if _live.get("thread") is not None:
        return
    from soniq import transcript

    def loop():
        while True:
            time.sleep(interval)
            try:
                lines = transcript.read_all()
                total = len(lines)
                if not _live["init"]:
                    _live["init"] = True
                    _live["seen"] = total
                    transcript.take_own()
                    continue
                if total < _live["seen"]:
                    _live["seen"] = total
                    transcript.take_own()
                    continue
                delta = total - _live["seen"]
                if delta <= 0:
                    continue
                new = lines[-delta:]
                own = transcript.take_own()
                _live["seen"] = total
                for text in _filter_own(new, own)[-60:]:
                    _live_print(text)
            except Exception:
                pass

    thread = threading.Thread(target=loop, daemon=True)
    _live["thread"] = thread
    thread.start()


_posix_loaded = 0


def _sync_readline(history: list[str]) -> None:
    """Feed new entries into the stdlib readline (POSIX only)."""
    global _posix_loaded
    import readline

    while _posix_loaded < len(history):
        readline.add_history(history[_posix_loaded])
        _posix_loaded += 1


def read_line(prompt: str, history: list[str]) -> str:
    """``input()`` replacement with history recall when on a terminal."""
    if not sys.stdin.isatty():
        return input(prompt)
    try:
        import readline  # noqa: F401
    except ImportError:
        readline = None
    if readline is not None:
        try:
            readline.set_history_length(1000)
            _sync_readline(history)
        except Exception:
            pass
        return input(prompt)
    try:
        import msvcrt  # noqa: F401
    except ImportError:
        return input(prompt)

    start_transcript_monitor()

    def write(text: str) -> None:
        out = getattr(sys.stdout, "stream", sys.stdout)
        out.write(text)
        out.flush()

    return _edit_line_from_keys(_read_key_windows, prompt, history, write)
