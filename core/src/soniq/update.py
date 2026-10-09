"""
update.py — Version check against the public repository.

When the interactive app starts it quietly asks GitHub for the newest
release of SoniQ (max ~3 s per request; any failure is ignored). If a
newer version exists, the app prints a one-line notice with the link.

Release files follow a fixed, parseable name scheme:
    soniq-v<MAJOR>.<MINOR>.<PATCH>-<target>.zip
    e.g. soniq-v0.2.13-github.zip

Two sources are tried: the GitHub Releases API first (it also exposes
asset names), then the plain VERSION file on the main branch — so the
check works even before any GitHub Release exists.
"""

import json
import re
import urllib.request
from typing import Optional, Tuple

from soniq import __version__

REPO = "reza3320/SoniQ"
ASSET_RE = re.compile(r"^soniq-v(\d+\.\d+\.\d+)-[A-Za-z0-9._-]+\.zip$")
_VERSION_RE = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")


def parse_version(text: str) -> Optional[Tuple[int, int, int]]:
    """Parse '1.2.3' (with optional v prefix) into (1, 2, 3)."""
    match = _VERSION_RE.search(text or "")
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _http_get(url: str, timeout: float = 3.0) -> Optional[str]:
    """GET a URL and return its body, or None on any failure."""
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": "SoniQ-UpdateCheck"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", "replace")
    except Exception:
        return None


def fetch_latest(timeout: float = 3.0) -> Optional[dict]:
    """Return {'version': 'x.y.z', 'url': ...} for the newest release, or None."""
    # 1) GitHub Releases API — primary source once releases exist
    data = _http_get(
        f"https://api.github.com/repos/{REPO}/releases/latest", timeout)
    if data:
        try:
            release = json.loads(data)
            version = parse_version(release.get("tag_name", ""))
            if version:
                return {
                    "version": ".".join(map(str, version)),
                    "url": (release.get("html_url")
                            or f"https://github.com/{REPO}"),
                }
        except json.JSONDecodeError:
            pass

    # 2) VERSION file on the main branch — works before any release exists
    data = _http_get(
        f"https://raw.githubusercontent.com/{REPO}/main/VERSION", timeout)
    if data:
        version = parse_version(data)
        if version:
            return {"version": ".".join(map(str, version)),
                    "url": f"https://github.com/{REPO}"}
    return None


def check_for_update(timeout: float = 3.0) -> Optional[dict]:
    """Compare the newest release with the running version.

    Returns {'version', 'url'} when a NEWER version exists; None in every
    other case (up to date, offline, no releases yet). Never raises.
    """
    try:
        latest = fetch_latest(timeout)
        if not latest:
            return None
        current = parse_version(__version__)
        newest = parse_version(latest.get("version", ""))
        if current and newest and newest > current:
            return latest
        return None
    except Exception:
        return None
