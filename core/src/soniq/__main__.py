#!/usr/bin/env python3
"""SoniQ — High-quality music downloader.

Usage:
    python -m soniq download "Artist - Title"
    python -m soniq batch songs.json
    python -m soniq --help
    python -m soniq                   (interactive mode)
"""

import os, sys, json
from pathlib import Path

_pkg_root = Path(__file__).resolve().parent.parent
_sibling = Path(__file__).resolve().parent
_parent_of_sibling = _sibling.parent
for path in [str(_pkg_root), str(_parent_of_sibling)]:
    if path not in sys.path:
        sys.path.insert(0, str(path))

from soniq import __version__, __app_name__
from soniq.cli import (
    parse_args, parse_artist_title, print_banner, print_help,
    print_result, print_diagnostics, show_diagnostics, run_batch,
    interactive_mode,
)
from soniq.config import Config
from soniq.diagnostics import get as diag, Diagnostics


def main():
    args = parse_args()

    # -- Diagnostics mode ------------------------------------------------
    if args.diagnostics:
        show_diagnostics(None)
        return

    # -- Help mode -------------------------------------------------------
    if args.command == "help":
        print_help()
        return

    # -- Session mode (headless worker for the tray front-end) -----------
    if args.command == "session":
        from soniq.session import run_session
        run_session(Config())
        return

    # -- Interactive mode (no command) -----------------------------------
    if args.command is None:
        config = Config()
        interactive_mode(config)
        return

    # -- Load configuration ----------------------------------------------
    config = Config()

    # -- Output directory ------------------------------------------------
    output_dir = args.output or config.get(
        "output_dir",
        default=str(Path.home() / "Music" / "SoniQ")
    )
    from soniq.fsutil import ensure_output_dir
    output_dir = ensure_output_dir(output_dir)

    # -- Import orchestrator ---------------------------------------------
    from soniq.orchestrator import Orchestrator
    orch = Orchestrator(config)

    # -- Single download -------------------------------------------------
    if args.command == "download":
        artist, title = parse_artist_title(args.args or [])
        if not artist or not title:
            print("Usage: soniq download \"Artist - Title\"")
            sys.exit(1)
        print_banner()
        print(f"Processing: {artist} - {title}\n")
        result = orch.process_song(artist, title, output_dir)
        print()
        print_result(result)
        _save_diagnostics()
        sys.exit(0 if result.get("status") == "success" else 1)

    # -- URL download ----------------------------------------------------
    if args.command == "url":
        print_banner()
        print(f"URL: {args.url}\n")
        result = orch.process_url(args.url, output_dir)
        print()
        print_result(result)
        _save_diagnostics()
        sys.exit(0 if result.get("status") == "success" else 1)

    # -- Playlist download -----------------------------------------------
    if args.command == "playlist":
        print_banner()
        print(f"Playlist: {args.url}\n")
        results = orch.process_playlist(args.url, output_dir)
        success = sum(1 for r in results if r.get("status") == "success")
        total = len(results)
        print(f"\nDone. {success}/{total} tracks completed successfully.")
        _save_diagnostics()
        sys.exit(0 if success == total else 1)

    # -- Batch download --------------------------------------------------
    if args.command == "batch":
        batch_file = args.file
        if not os.path.exists(batch_file):
            print(f"Error: file not found: {batch_file}")
            sys.exit(1)
        print_banner()
        print(f"Batch file: {batch_file}\n")
        results = run_batch(orch, batch_file, output_dir, config)
        success = sum(1 for r in results if r.get("status") == "success")
        total = len(results)
        print(f"\nDone. {success}/{total} songs completed successfully.")
        _save_diagnostics()
        sys.exit(0 if success == total else 1)


def _save_diagnostics():
    diag_dir = str(Path.home() / ".soniq" / "diagnostics")
    os.makedirs(diag_dir, exist_ok=True)
    report_path = os.path.join(diag_dir, f"{diag().filename_id}.json")
    diag().to_json(report_path)


if __name__ == "__main__":
    main()
