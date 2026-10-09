"""fsutil.py — Windows-safe filesystem helpers.

SoniQ's default output location is ``~/Music/SoniQ``. On Windows that
path can be a *dangling junction* (OneDrive-redirected Music library
that no longer exists) or shadowed by a file, which makes
``os.makedirs`` raise ``FileNotFoundError: [WinError 2]``. These
helpers make directory creation self-healing and filenames safe.
"""

import os
import re
from pathlib import Path

# Characters Windows forbids in file/directory names, plus control chars.
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# Reserved device names (with or without extension, case-insensitive).
_RESERVED = re.compile(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$', re.I)


def sanitize_filename(name: str, max_len: int = 150) -> str:
    """Return *name* safe to use as a Windows file or directory name."""
    name = _INVALID_CHARS.sub("_", name or "").strip()
    name = name.rstrip(". ")  # Windows silently drops trailing dots/spaces
    if not name:
        name = "download"
    if _RESERVED.match(name):
        name = f"_{name}"
    if len(name) > max_len:
        stem, dot, ext = name.rpartition(".")
        if dot and len(ext) <= 10:
            name = stem[: max_len - len(ext) - 1] + dot + ext
        else:
            name = name[:max_len]
    return name


def ensure_output_dir(output_dir: str) -> str:
    """Create *output_dir* (including parents) and return it.

    If creation fails (Windows WinError 2: dangling junction, a path
    component is a file, drive unavailable), fall back to a location
    that is guaranteed to exist: ``~/SoniQ``, then the working dir.
    Prints a warning so the user knows where files went.
    """
    try:
        os.makedirs(output_dir, exist_ok=True)
        return output_dir
    except OSError as exc:
        fallback = str(Path.home() / "SoniQ")
        try:
            os.makedirs(fallback, exist_ok=True)
        except OSError:
            fallback = os.getcwd()
            os.makedirs(fallback, exist_ok=True)
        print(f"  ! Output dir unavailable ({output_dir}): {exc}")
        print(f"  ! Using instead: {fallback}")
        return fallback


def clean_youtube_url(url: str) -> str:
    """Strip radio/playlist noise (list=, start_radio=, index=, feature=)
    from a YouTube watch URL.

    Radio/mix URLs are bot-check magnets and the extra params are never
    needed for a single-video download. Returns the URL unchanged if it
    is not a YouTube link or cannot be parsed.
    """
    try:
        from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
        parts = urlparse(url)
        is_watch = parts.path in ("", "/watch", "/watch/") or \
            "youtu.be" in (parts.netloc or "")
        if is_watch and ("youtube.com" in (parts.netloc or "") or
                         "youtu.be" in (parts.netloc or "")):
            keep = {k: v[0] for k, v in parse_qs(parts.query).items()
                    if k not in ("list", "start_radio", "index",
                                 "feature", "continue")}
            return urlunparse(parts._replace(query=urlencode(keep)))
    except Exception:
        pass
    return url
