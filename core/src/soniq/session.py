"""
session.py — Headless worker mode for the tray front-end.

Started with ``run.py session``. Speaks newline-delimited JSON on
stdin/stdout (one JSON object per line):

    {"type": "ready",    "version": "0.2.17"}
    {"type": "log",      "text": "..."}        human text during a job
    {"type": "progress", "pct": 43.2, "text": "..."}
    {"type": "result",   "song": {...}}        per-song outcome
    {"type": "done",     "cancelled": false}   end of one command
    {"type": "error",    "message": "..."}     bad command / crash
    {"type": "cancelled"}                      cancel acknowledged
    {"type": "bye"}

Commands (same vocabulary as the interactive app):
    /download Artist - Title | /url <url> | /playlist <url> |
    /batch <file> | /output [path] | /version | /help | /cancel | /quit
"""

import contextlib
import io
import json
import queue
import re
import sys
import threading
from pathlib import Path

from soniq import __version__, procutil
from soniq.config import Config
from soniq.diagnostics import get as diag
from soniq.fsutil import ensure_output_dir

_PROGRESS_RE = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%")


def _emit(obj: dict) -> None:
    """Write one protocol line (bypasses any print() redirection)."""
    sys.__stdout__.write(json.dumps(obj) + "\n")
    sys.__stdout__.flush()


class _Capture:
    """File-like object turning print() output into log events."""

    def write(self, text):
        for line in text.splitlines():
            if line.strip():
                _emit({"type": "log", "text": line.rstrip()})
        return len(text)

    def flush(self):
        pass


def _on_child_line(line: str) -> None:
    """Forward child-process output (progress lines get a type of their own)."""
    match = _PROGRESS_RE.search(line)
    if match:
        _emit({"type": "progress", "pct": float(match.group(1)),
               "text": line.strip()})
    else:
        _emit({"type": "log", "text": line.rstrip()})


def _emit_song(result: dict) -> None:
    _emit({"type": "result", "song": {
        "artist": result.get("artist", ""),
        "title": result.get("title", ""),
        "status": result.get("status", ""),
        "quality": result.get("quality", ""),
        "file": result.get("filepath", ""),
        "error": result.get("error", ""),
        "error_code": result.get("error_code", ""),
    }})


def _dispatch(line: str, ctx: dict) -> None:
    """Execute one command line. Output goes through _Capture/_emit only."""
    config = ctx["config"]
    orch = ctx["orch"]

    if line == "/version":
        _emit({"type": "log", "text": f"SoniQ v{__version__}"})
        return

    if line == "/help":
        _emit({"type": "log", "text": (
            "Commands: /download Artist - Title | /url <url> | "
            "/playlist <url> | /batch <file> | /output [path] | "
            "/retry (re-run the last failures) | /cancel | /quit")})
        return

    if line == "/retry":
        pending = list(ctx.get("failed_cmds") or [])
        if not pending:
            _emit({"type": "log", "text": "(nothing to retry)"})
            return
        _emit({"type": "log",
               "text": f"Retrying {len(pending)} failed song(s)..."})
        remaining = []
        for command in pending:
            _dispatch(command, ctx)
            remaining.extend(ctx.get("failed_cmds") or [])
        ctx["failed_cmds"] = remaining
        return

    if line.startswith("/output"):
        arg = line[len("/output"):].strip().strip('"')
        if not arg:
            _emit({"type": "log",
                   "text": f"Downloads are saved to: {ctx['output_dir']}"})
        else:
            ctx["output_dir"] = ensure_output_dir(arg)
            config.set("output_dir", ctx["output_dir"])
            config.set("output_dir_chosen", True)
            _emit({"type": "log", "text":
                   f"Downloads will be saved to: {ctx['output_dir']}"})
        return

    if line.startswith("/download"):
        parts = line[len("/download"):].strip()
        if " - " not in parts:
            _emit({"type": "error",
                   "message": "Usage: /download Artist - Title"})
            return
        artist, title = parts.split(" - ", 1)
        artist, title = artist.strip(), title.strip()
        result = orch.process_song(artist, title, ctx["output_dir"])
        _emit_song(result)
        if result.get("status") == "success":
            ctx["failed_cmds"] = []
        else:
            ctx["failed_cmds"] = [f"/download {artist} - {title}"]
        return

    if line.startswith("/url"):
        url = line[len("/url"):].strip()
        if not url:
            _emit({"type": "error", "message": "Usage: /url <youtube-url>"})
            return
        result = orch.process_url(url, ctx["output_dir"])
        _emit_song(result)
        if result.get("status") == "success":
            ctx["failed_cmds"] = []
        else:
            ctx["failed_cmds"] = [f"/url {url}"]
        return

    if line.startswith("/playlist"):
        url = line[len("/playlist"):].strip()
        if not url:
            _emit({"type": "error",
                   "message": "Usage: /playlist <youtube-url>"})
            return
        results = orch.process_playlist(url, ctx["output_dir"])
        for r in results:
            _emit_song(r)
        failed = [r for r in results if r.get("status") != "success"]
        ctx["failed_cmds"] = [
            f"/download {r.get('artist', '')} - {r.get('title', '')}"
            for r in failed if r.get("artist") or r.get("title")]
        done = len(results) - len(failed)
        _emit({"type": "log",
               "text": f"Playlist done: {done}/{len(results)}"})
        return

    if line.startswith("/batch"):
        path = line[len("/batch"):].strip()
        if not path:
            _emit({"type": "error", "message": "Usage: /batch <file>"})
            return
        from soniq.cli import run_batch
        results = run_batch(orch, path, ctx["output_dir"], config)
        for r in results:
            _emit_song(r)
        failed = [r for r in results if r.get("status") != "success"]
        ctx["failed_cmds"] = [
            f"/download {r.get('artist', '')} - {r.get('title', '')}"
            for r in failed if r.get("artist") or r.get("title")]
        return

    _emit({"type": "error", "message": f"Unknown command: {line}"})


def run_session(config: Config = None) -> None:
    """Main worker loop. Exits on /quit or stdin EOF."""
    config = config or Config()
    try:
        # The tray host writes UTF-8; make sure we decode it the same way.
        sys.stdin = io.TextIOWrapper(sys.stdin.buffer,
                                     encoding="utf-8", errors="replace")
    except Exception:
        pass
    procutil.set_line_hook(_on_child_line)
    capture = _Capture()
    lines = queue.Queue()

    def reader():
        try:
            for raw in sys.stdin:
                lines.put(raw.rstrip("\n"))
        except Exception:
            pass
        lines.put(None)  # EOF marker

    threading.Thread(target=reader, daemon=True).start()

    from soniq.orchestrator import Orchestrator
    with contextlib.redirect_stdout(capture):
        orch = Orchestrator(config)
        output_dir = ensure_output_dir(config.get(
            "output_dir", default=str(Path.home() / "Music" / "SoniQ")))

    ctx = {"config": config, "orch": orch, "output_dir": output_dir,
           "failed_cmds": []}
    _emit({"type": "ready", "version": __version__})

    while True:
        line = lines.get()
        if line is None:
            break
        line = line.strip()
        if not line:
            continue
        if line in ("/quit", "/exit"):
            break
        if line == "/cancel":
            procutil.cancel_active()
            _emit({"type": "cancelled"})
            continue

        procutil.clear_cancel()
        try:
            waiting = lines.qsize()
        except Exception:
            waiting = 0
        if waiting:
            _emit({"type": "log",
                   "text": f"({waiting} more command(s) waiting)"})
        try:
            with contextlib.redirect_stdout(capture):
                _dispatch(line, ctx)
            _emit({"type": "done",
                   "cancelled": procutil.cancel_requested()})
        except Exception as exc:
            _emit({"type": "error",
                   "message": f"{type(exc).__name__}: {exc}"})
        procutil.clear_cancel()

        # Keep the diagnostics history fresh for /diagnostics and support.
        try:
            diag_dir = Path.home() / ".soniq" / "diagnostics"
            diag_dir.mkdir(parents=True, exist_ok=True)
            diag().to_json(str(diag_dir / f"{diag().filename_id}.json"))
        except Exception:
            pass

    _emit({"type": "bye"})
