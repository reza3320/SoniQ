"""
cli.py — Command-line interface and terminal output.

This module handles user interaction: parsing command-line arguments,
displaying the application banner, printing progress, and showing help.

No magic here — just straightforward terminal I/O that makes the
application pleasant to use.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from soniq import __version__, __app_name__
from soniq.diagnostics import get as diag


def show_diagnostics(config) -> None:
    """Display the last diagnostics report."""
    diag_dir = str(Path.home() / ".soniq" / "diagnostics")
    if not os.path.exists(diag_dir):
        print("No diagnostics reports found.\nRun a download first.")
        return
    files = sorted(Path(diag_dir).iterdir(), key=os.path.getmtime, reverse=True)
    if not files:
        print("No diagnostics reports found.")
        return
    with open(files[0]) as f:
        report = json.load(f)
    print(f"\nRun ID: {report.get('run_id', '?')}")
    print(f"  Total: {report.get('total', 0)}")
    print(f"  OK: {report.get('success', 0)}")
    print(f"  Failed: {report.get('failed', 0)}")
    print(f"  Skipped: {report.get('skipped', 0)}")
    summary = report.get("summary", {})
    if summary:
        print(f"  Qualities: {summary.get('quality_breakdown', {})}")
        print(f"  Duration: {summary.get('total_duration_seconds', 0)}s")
    failed = [s for s in report.get("songs", []) if s.get("status") == "failed"]
    if failed:
        print("\n  Failed songs:")
        for s in failed:
            print(f"    [{s.get('error_code','?')}] {s.get('artist')} - {s.get('title')}: {s.get('error_message','?')}")


def _save_run_diag() -> None:
    """Persist the current run's diagnostics to ~/.soniq/diagnostics/."""
    diag_dir = str(Path.home() / ".soniq" / "diagnostics")
    os.makedirs(diag_dir, exist_ok=True)
    diag().to_json(os.path.join(diag_dir, f"{diag().filename_id}.json"))


def run_batch(orch, file_path: str, output_dir: str, config) -> list[dict]:
    """Run a batch from JSON or CSV file."""
    path = Path(file_path)
    if not path.exists():
        print(f"File not found: {file_path}")
        return []
    ext = path.suffix.lower()
    if ext == ".json":
        with open(path) as f:
            data = json.load(f)
        songs = data.get("songs", data if isinstance(data, list) else [])
        settings = data.get("settings", {})
    elif ext == ".csv":
        import csv
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            songs = [{"artist": r.get("artist","").strip(), "title": r.get("title","").strip()}
                     for r in reader if r.get("artist") and r.get("title")]
        settings = {}
    else:
        print(f"Unsupported file format: {ext}")
        return []
    if not songs:
        print("No songs found in the file.")
        return []
    print(f"Processing {len(songs)} songs...")
    # Note: the batch file's "settings" block is informational only — the
    # output directory comes from the CLI/config. (An earlier call passed
    # settings as a third positional arg — every batch run crashed.)
    results = orch.process_batch(songs, output_dir)
    return results


def interactive_help() -> None:
    """Print help in interactive mode."""
    print("""
Commands:
  /help                    Show this help
  /version                 Show version
  /output [path]           Show or change where songs are saved
  /diagnostics             Show last run diagnostics
  /download Artist - Title Download one song (best audio upload, ranked)
  /url <youtube-url>       Download an exact YouTube URL
  /playlist <youtube-url>  Download a whole YouTube playlist
  /batch <file>            Batch download from JSON/CSV
  /history                 Show recent commands (shared with the tray)
  /quit or /exit           Exit
""")


def _process_download_line(orch, parts: str, output_dir: str):
    """Handle a /download line — order-agnostic artist/title splitting."""
    if " - " in parts:
        a, t = parts.split(" - ", 1)
        result = orch.process_song(a.strip(), t.strip(), output_dir)
        print_result(result)
        _save_run_diag()
    else:
        print("Usage: /download Artist - Title")


def _first_run_setup(config) -> None:
    """First launch: ask where songs should be saved.

    Asks again on every launch until a choice is recorded. The answer
    is stored in the config; change it later with /output <path>.
    """
    if config.get("output_dir_chosen"):
        return
    from soniq.fsutil import ensure_output_dir
    default = str(Path.home() / "Music" / "SoniQ")
    print()
    print("  Where should your downloaded songs be saved?")
    print(f"  Press Enter to use the default: {default}")
    try:
        answer = input("  Save to: ").strip().strip('"')
    except (EOFError, KeyboardInterrupt):
        print()
        return  # not chosen — ask again next launch
    chosen = ensure_output_dir(answer or default)
    config.set("output_dir", chosen)
    config.set("output_dir_chosen", True)
    print(f"  OK — songs will be saved to: {chosen}")
    print()


def _start_update_check() -> None:
    """Quietly look for a newer version in the background.

    Runs in a daemon thread so it can never block or slow the app; if a
    newer release exists it prints a one-line notice, otherwise nothing.
    """
    import threading

    def worker():
        from soniq.update import check_for_update
        found = check_for_update()
        if found:
            print(f"\n  A newer version v{found['version']} is available:"
                  f"\n    {found['url']}\n")

    try:
        threading.Thread(target=worker, daemon=True).start()
    except Exception:
        pass


_CLI_MUTEX_HANDLE = None


def _cli_already_open() -> bool:
    """Windows: True when another SoniQ CLI console is already running.

    Uses a named mutex; best-effort brings the existing window forward.
    On other platforms (or any failure) it simply returns False.
    """
    global _CLI_MUTEX_HANDLE
    try:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.CreateMutexW(None, False, "Local\\SoniQ_CLI_Console")
        if not handle:
            return False
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            try:
                user32 = ctypes.windll.user32
                for cls in ("ConsoleWindowClass",
                            "CASCADIA_HOSTING_WINDOW_CLASS"):
                    hwnd = user32.FindWindowW(cls, "SoniQ")
                    if hwnd:
                        user32.SetForegroundWindow(hwnd)
                        break
            except Exception:
                pass
            return True
        _CLI_MUTEX_HANDLE = handle  # keep alive for this process
        return False
    except Exception:
        return False


def interactive_mode(config) -> None:
    """Run in interactive REPL mode."""
    if _cli_already_open():
        print()
        print("  SoniQ CLI is already open in another window.")
        print("  Closing this extra window...")
        import time

        time.sleep(1.5)
        raise SystemExit(2)
    from soniq.orchestrator import Orchestrator
    from soniq.fsutil import ensure_output_dir
    from soniq.lineedit import append_history, load_history, read_line
    from soniq import transcript
    orch = Orchestrator(config)
    print_banner()
    print(WELCOME_TEXT)
    _first_run_setup(config)
    if config.get("check_for_updates", True):
        _start_update_check()
    output_dir = ensure_output_dir(config.get(
        "output_dir", default=str(Path.home() / "Music" / "SoniQ")))
    previous = transcript.read_tail(25)
    if previous:
        print("  --- previous messages ---")
        for item in previous:
            print(item)
        print("  --- new session ---")
        print()
    transcript.start_capture()
    hist = load_history()
    while True:
        try:
            line = read_line("soniq> ", hist).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        transcript.clear_pending()
        if line in ("/quit", "/exit"):
            break
        try:
            transcript.write_line("soniq> " + line)
        except Exception:
            pass
        if line == "/help":
            interactive_help()
        elif line == "/version":
            print(f"{__app_name__} v{__version__}")
        elif line == "/history":
            entries = load_history()
            recent = entries[-15:]
            if not recent:
                print("  (no history yet)")
            else:
                for i, item in enumerate(recent, 1):
                    print(f"  {i:2d}. {item}")
        elif line.startswith("/output"):
            arg = line[len("/output"):].strip().strip('"')
            if not arg:
                print(f"  Downloads are saved to: {output_dir}")
                print("  Change it with: /output <path>")
            else:
                output_dir = ensure_output_dir(arg)
                config.set("output_dir", output_dir)
                config.set("output_dir_chosen", True)
                print(f"  Downloads will be saved to: {output_dir}")
        elif line == "/diagnostics":
            show_diagnostics(config)
        elif line.startswith("/download"):
            parts = line[len("/download"):].strip()
            _process_download_line(orch, parts, output_dir)
        elif line.startswith("/url"):
            url = line[len("/url"):].strip()
            if url:
                result = orch.process_url(url, output_dir)
                print_result(result)
                _save_run_diag()
            else:
                print("Usage: /url <youtube-url>")
        elif line.startswith("/playlist"):
            url = line[len("/playlist"):].strip()
            if url:
                results = orch.process_playlist(url, output_dir)
                print(f"Done: {sum(1 for r in results if r['status']=='success')}/{len(results)} complete")
                _save_run_diag()
            else:
                print("Usage: /playlist <youtube-url>")
        elif line.startswith("/batch"):
            path = line[len("/batch"):].strip()
            if path:
                results = run_batch(orch, path, output_dir, config)
                print(f"Done: {sum(1 for r in results if r['status']=='success')}/{len(results)} complete")
                _save_run_diag()
            else:
                print("Usage: /batch <file.json>")
        else:
            print(f"Unknown: {line}. Type /help")
        try:
            append_history(line)
        except Exception:
            pass
        hist.append(line)


# -- ASCII Art Banner --------------------------------------------------------

BANNER = r"""
                .-.
               (   )
                | |
                | |
    ,__________| |__________
   |  ________   ________  |
   | |        | |        | |
   | |  SoniQ | |  v""" + __version__ + """  | |
   | |________| |________| |
   |_______________________|
        _|___________|_
       /_______________\\
       |||||||||||||||||
"""


# -- Welcome / Help Text -----------------------------------------------------

WELCOME_TEXT = f"""
{__app_name__} downloads music from the internet at the highest possible quality.

It automatically selects the best available source for each song.
You do not need to know or care where the music comes from.
The application handles everything transparently.

Type /help for commands, /quit to exit.
"""

HELP_TEXT = f"""
{__app_name__} downloads music from the internet at the highest possible quality.

It automatically selects the best available source for each song.
You do not need to know or care where the music comes from.
The application handles everything transparently.

Usage examples:
  {__app_name__.lower()} download "Artist - Title"
  {__app_name__.lower()} download "Artist" "Title"
  {__app_name__.lower()} url "https://youtube.com/watch?v=..."
  {__app_name__.lower()} playlist "https://youtube.com/playlist?list=..."
  {__app_name__.lower()} batch songs.json
  {__app_name__.lower()} batch songs.csv
  {__app_name__.lower()} --diagnostics

Songs are picked as the best official AUDIO upload (ranked search):
music videos, live versions, remixes and covers are skipped automatically.

For batch operations, provide a JSON file with this structure:
  {{
    "songs": [
      {{"artist": "Artist Name", "title": "Song Title"}}
    ],
    "settings": {{
      "output_dir": "./downloads"
    }}
  }}

Or a CSV file with columns: artist, title

Diagnostics from the last run are saved to ~/.soniq/diagnostics/
View them with: {__app_name__.lower()} --diagnostics
"""


# -- Output Helpers ----------------------------------------------------------

def print_banner():
    """Display the application banner."""
    print(BANNER)
    print(f"  {__app_name__} v{__version__}")
    print(f"  High-quality music downloader")
    print()


def print_help():
    """Display the full help text."""
    print_banner()
    print(HELP_TEXT)


def print_progress(current: int, total: int, label: str = ""):
    """Print a simple progress indicator."""
    bar_length = 30
    fraction = current / total if total > 0 else 0
    filled = int(bar_length * fraction)
    bar = "#" * filled + "." * (bar_length - filled)
    pct = int(fraction * 100)
    print(f"\r  {label} [{bar}] {pct}%", end="")
    if current >= total:
        print()


def print_result(result: dict):
    """Print a single song result in a clean format."""
    artist = result.get("artist", "?")
    title = result.get("title", "?")
    status = result.get("status", "?")
    quality = result.get("quality", "?")
    filepath = result.get("filepath", "")

    if status == "success":
        status_str = "OK"
    elif status == "failed":
        status_str = "FAILED"
    else:
        status_str = status.upper()

    print(f"  {artist} - {title}")
    print(f"    Status: {status_str}")
    if status == "success":
        print(f"    Quality: {quality}")
        print(f"    File: {filepath}")
    else:
        err = result.get("error", "")
        code = result.get("error_code", "")
        if err:
            detail = f"[{code}] {err}" if code else err
            print(f"    Last error: {detail}")
        else:
            print(f"    Last error: Check diagnostics for details")


def print_diagnostics(diag_path: str):
    """Display the most recent diagnostics report."""
    if not os.path.exists(diag_path):
        print("No diagnostics report found.")
        print("Run a download first, then check again.")
        return

    try:
        with open(diag_path) as f:
            report = json.load(f)
    except (json.JSONDecodeError, OSError):
        print("Could not read diagnostics file.")
        return

    summary = report.get("summary", {})
    print(f"\n  Run ID: {report.get('run_id', 'unknown')}")
    print(f"  Total: {report.get('total', 0)}")
    print(f"  OK: {report.get('success', 0)}")
    print(f"  Failed: {report.get('failed', 0)}")
    print(f"  Skipped: {report.get('skipped', 0)}")

    if summary:
        print(f"  Qualities: {summary.get('quality_breakdown', {})}")
        print(f"  Duration: {summary.get('total_duration_seconds', 0)} seconds")

    failed_songs = [s for s in report.get("songs", []) if s.get("status") == "failed"]
    if failed_songs:
        print(f"\n  Failed songs:")
        for s in failed_songs:
            ec = s.get("error_code", "?")
            em = s.get("error_message", "No details")
            print(f"    [{ec}] {s.get('artist')} - {s.get('title')}: {em}")


# -- Argument Parsing --------------------------------------------------------

def parse_args(argv: list = None) -> argparse.Namespace:
    """
    Parse command-line arguments.

    Supports subcommands: download, batch, help
    And flags: --version, --diagnostics, --output
    """
    parser = argparse.ArgumentParser(
        prog=__app_name__.lower(),
        description=f"{__app_name__} — High-quality music downloader",
        add_help=False,
    )

    parser.add_argument("--version", "-v", action="version",
                        version=f"{__app_name__} v{__version__}")

    parser.add_argument("--diagnostics", action="store_true",
                        help="Show the last run diagnostics")

    parser.add_argument("--output", "-o", default="",
                        help="Output directory for downloaded files")

    parser.add_argument("--help", action="store_true",
                        help="Show this help message")

    subparsers = parser.add_subparsers(dest="command")

    # download subcommand
    dl = subparsers.add_parser("download", help="Download one song")
    dl.add_argument("args", nargs="*", help="Artist name or 'Artist - Title'")

    # batch subcommand
    batch = subparsers.add_parser("batch", help="Batch download from file")
    batch.add_argument("file", help="Path to JSON or CSV batch file")

    # url subcommand
    u = subparsers.add_parser("url", help="Download an exact YouTube URL")
    u.add_argument("url", help="YouTube watch URL")

    # playlist subcommand
    pl = subparsers.add_parser("playlist", help="Download a whole YouTube playlist")
    pl.add_argument("url", help="YouTube playlist URL")

    # session subcommand — headless worker used by the tray front-end
    subparsers.add_parser("session",
                          help="Run as a headless worker (used by the tray)")

    # help subcommand
    subparsers.add_parser("help", help="Show detailed help")

    args = parser.parse_args(argv)

    # Fix (2026-08-05): previously `or not args.command` forced command="help"
    # whenever no subcommand was given, making the interactive REPL
    # unreachable (double-clicking app.bat always printed help and exited).
    # Now only an explicit --help forces help; None flows through so
    # __main__ dispatches to interactive_mode().
    if args.help:
        args.command = "help"

    return args


def parse_artist_title(args_list: list) -> tuple:
    """
    Parse artist and title from command arguments.

    Accepts:
      "Artist - Title"  -> ("Artist", "Title")
      ["Artist", "Title"] -> ("Artist", "Title")
    """
    full = " ".join(args_list)
    if " - " in full:
        parts = full.split(" - ", 1)
        return parts[0].strip(), parts[1].strip()
    if len(args_list) >= 2:
        return args_list[0].strip(), " ".join(args_list[1:]).strip()
    return full.strip(), ""
