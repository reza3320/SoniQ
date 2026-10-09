"""
provider_primary.py — High-quality audio source provider.

This module handles the primary music source which offers direct
high-bitrate MP3 downloads (320 kbps). When this source is available,
it provides the best quality-to-convenience ratio.

The source may occasionally be unreachable due to regional network
conditions. When that happens, the module detects the downtime and
reports it clearly so the orchestrator can fall back gracefully.
"""

import os
import re
import time
import urllib.request
import urllib.error
import urllib.parse
from html.parser import HTMLParser
from typing import Optional

from soniq.diagnostics import get as diag


# -- Request Headers ----------------------------------------------------------
# Standard browser headers to avoid being blocked by CDN services.

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}


# -- Quality Descriptor ------------------------------------------------------

class SourceQuality:
    """
    Represents a single quality option available for download.

    Attributes:
        label:     Human-readable quality label, e.g. "320", "256"
        url:       Direct download URL for the audio file
        bitrate:   Bitrate in kbps (approximate)
        is_online: Whether this quality is currently fetchable
    """

    TIERS = {"320": 5, "256": 4, "128": 2}

    def __init__(self, label: str, url: str, bitrate: int):
        self.label = label
        self.url = url
        self.bitrate = bitrate
        self.is_online = True

    @property
    def tier(self) -> int:
        """Higher number = better quality."""
        return self.TIERS.get(self.label, 0)

    def __lt__(self, other: "SourceQuality") -> bool:
        return self.tier < other.tier


# -- Source Availability Checker ---------------------------------------------

def check_source_online() -> tuple[bool, str]:
    """
    Check whether the primary source is currently reachable.

    Some regions experience periodic network disruptions that can last
    from minutes to days. This function detects those conditions so the
    application can adapt its behaviour.

    Returns:
        (is_online: bool, message: str)
        If offline, message explains what the user can expect.
    """
    test_url = PrimaryProvider.BASE_URL
    try:
        req = urllib.request.Request(test_url, headers=HEADERS)
        resp = urllib.request.urlopen(req, timeout=10)
        return True, "Source is responding normally."
    except urllib.error.URLError as e:
        reason = str(e.reason) if hasattr(e, 'reason') else str(e)
        if "Name or service not known" in reason or "Temporary failure" in reason:
            msg = (
                "The high-quality source is currently unreachable due to "
                "regional network restrictions. This is usually temporary "
                "and may resolve within hours to days. Want to wait or "
                "fall back to the alternative source now?"
            )
            return False, msg
        elif "timed out" in reason:
            msg = (
                "The high-quality source is responding slowly or is "
                "temporarily overloaded. The alternative source is ready "
                "if you prefer not to wait."
            )
            return False, msg
        return False, f"Source check failed: {reason}"
    except Exception as e:
        return False, f"Could not verify source status: {e}"


# -- HTML Parser for Search Results ------------------------------------------

class SearchResultParser(HTMLParser):
    """
    Parses search result pages to find matching songs.

    The search page lists multiple songs as article cards. Each card
    contains a heading with the song name and a link to its download page.
    This parser extracts those pairs.
    """

    def __init__(self):
        super().__init__()
        self.results: list[tuple[str, str]] = []
        self._in_heading = False
        self._buffer = ""
        self._current_url = ""

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag in ("h1", "h2", "h3", "h4"):
            self._in_heading = True
            self._buffer = ""
        if tag == "a" and "href" in d:
            href = d["href"]
            if "/download-song/" in href:
                self._current_url = href

    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "h3", "h4"):
            self._in_heading = False
            if self._current_url and "/download-song/" in self._current_url:
                text = self._buffer.strip()
                if text and "نتیجه جستجوی" not in text:
                    self.results.append((text, self._current_url))
            self._current_url = ""

    def handle_data(self, data):
        if self._in_heading:
            self._buffer += data


# -- Primary Source Provider -------------------------------------------------

class PrimaryProvider:
    """
    High-quality music source offering direct MP3 downloads.

    This provider delivers the best available quality (320 kbps MP3).
    It is the preferred source whenever it is reachable and has the
    requested song.

    Search flow:
        1. Send query to search endpoint
        2. Parse result cards to find matching songs
        3. Open the song's dedicated page to find download URLs
        4. Select the highest quality available
    """

    BASE_URL = "https://musics-fa.com"
    SEARCH_URL = BASE_URL + "/search/{query}"
    CDN_URL = "https://dls.musics-fa.com"
    TIMEOUT_SHORT = 10   # For connectivity checks
    TIMEOUT_LONG = 30    # For file downloads

    def __init__(self):
        self._last_request = 0.0

    # -- Polite Rate Limiting ---------------------------------------------
    # We wait a small amount between requests to avoid overwhelming the
    # source server. This is standard practice for automated tools.

    def _wait(self):
        elapsed = time.time() - self._last_request
        if elapsed < 0.5:
            time.sleep(0.5 - elapsed)
        self._last_request = time.time()

    # -- Search -----------------------------------------------------------

    def search(self, artist: str, title: str) -> list[dict]:
        """
        Search for a song on the primary source.

        Args:
            artist: Artist name
            title:  Song title

        Returns:
            List of dicts with keys: title, url
            Empty list if nothing was found or source is offline.
        """
        query = f"{artist} {title}"
        url = self.SEARCH_URL.format(query=urllib.parse.quote(query))
        self._wait()

        try:
            req = urllib.request.Request(url, headers=HEADERS)
            resp = urllib.request.urlopen(req, timeout=self.TIMEOUT_SHORT)
            html = resp.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as e:
            # The source may be down due to regional network disruptions.
            # Check connectivity to give a precise error.
            is_online, msg = check_source_online()
            if not is_online:
                diag().add_step("primary_search", "failed",
                                error_code="ERR_SRC_008",
                                error_message=msg)
            else:
                diag().add_step("primary_search", "failed",
                                error_code="ERR_NET_001",
                                error_message=str(e.reason))
            return []
        except Exception as e:
            diag().add_step("primary_search", "failed",
                            error_code="ERR_NET_001", error_message=str(e))
            return []

        # Parse the response HTML to extract song listings.
        parser = SearchResultParser()
        parser.feed(html)

        results = []
        for heading, song_url in parser.results:
            results.append({"title": heading, "url": song_url})

        return results

    # -- Quality Extraction -----------------------------------------------

    def get_download_urls(self, song_page_url: str) -> dict[str, str]:
        """
        Open a song's page and find all available MP3 download URLs.

        Returns a dictionary mapping quality labels to URLs:
            {"320": "https://...", "128": "https://..."}
        Empty dict if no downloads are available on the page.
        """
        if not song_page_url.startswith("http"):
            song_page_url = self.BASE_URL + song_page_url
        # Page links can carry raw spaces or non-ASCII characters; encode
        # them so the request layer accepts the URL.
        song_page_url = urllib.parse.quote(song_page_url, safe=":/?#[]@!$&'()*+,;=%")
        self._wait()

        try:
            req = urllib.request.Request(song_page_url, headers=HEADERS)
            resp = urllib.request.urlopen(req, timeout=self.TIMEOUT_SHORT)
            html = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            diag().add_step("primary_page", "failed",
                            error_code="ERR_SRC_003",
                            error_message=f"HTTP {e.code}")
            return {}
        except Exception as e:
            diag().add_step("primary_page", "failed",
                            error_code="ERR_SRC_003", error_message=str(e))
            return {}

        # Look for MP3 download links from the content delivery network.
        cdn_escaped = re.escape(self.CDN_URL)
        pattern = rf'({cdn_escaped}/(?:song/[^"\']+|tagdl/downloads/[^"\']+\.mp3))'
        matches = re.findall(pattern, html)

        urls = {}
        for match in matches:
            # Determine quality from surrounding context on the page.
            ctx_start = max(0, html.find(match) - 200)
            ctx_end = min(len(html), html.find(match) + len(match) + 200)
            ctx = html[ctx_start:ctx_end].lower()

            if "320" in ctx:
                urls["320"] = match
            elif "128" in ctx:
                urls["128"] = match
            else:
                # When quality is ambiguous, default to the first found URL.
                urls.setdefault("unknown", match)

        return urls

    # -- Download ---------------------------------------------------------

    def download(self, url: str, output_path: str) -> Optional[str]:
        """
        Download an audio file from the primary source.

        Args:
            url:          Direct MP3 download URL
            output_path:  Where to save the file on disk

        Returns:
            The output_path on success, None on failure.
        """
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        self._wait()

        # Download URLs can carry raw spaces or non-ASCII characters;
        # encode them so the request layer accepts the URL.
        url = urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%")

        try:
            req = urllib.request.Request(url, headers=HEADERS)
            resp = urllib.request.urlopen(req, timeout=self.TIMEOUT_LONG)
            with open(output_path, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)

            if os.path.getsize(output_path) == 0:
                os.remove(output_path)
                diag().add_step("primary_download", "failed",
                                error_code="ERR_SRC_006")
                return None
            return output_path

        except urllib.error.HTTPError as e:
            if e.code == 404:
                diag().add_step("primary_download", "failed",
                                error_code="ERR_SRC_004",
                                error_message="Download link has expired")
            else:
                diag().add_step("primary_download", "failed",
                                error_code="ERR_SRC_005",
                                error_message=f"HTTP {e.code}")
            return None
        except urllib.error.URLError as e:
            diag().add_step("primary_download", "failed",
                            error_code="ERR_SRC_005",
                            error_message=str(e.reason))
            return None
        except Exception as e:
            diag().add_step("primary_download", "failed",
                            error_code="ERR_SRC_005", error_message=str(e))
            return None

    # -- High-level convenience -------------------------------------------

    def best_quality(self, artist: str, title: str) -> Optional[SourceQuality]:
        """
        Find the best available quality for a song on the primary source.

        Returns a SourceQuality object, or None if the song was not found
        or the source is unreachable.
        """
        # Step 1: Soft reachability check — the search site can still be up
        # even when the CDN (or the route to it) is down, so a failed check
        # is logged but never blocks the search.
        is_online, msg = check_source_online()
        if not is_online:
            diag().add_step("primary_connectivity", "warning",
                            error_code="ERR_SRC_008",
                            error_message=msg)

        # Step 2: Search for the song.
        results = self.search(artist, title)
        if not results:
            return None

        # Step 3: Find the best-matching result.
        target_title = f"{artist} {title}".lower()
        best_result = None
        best_score = 0

        for r in results:
            rt = r["title"].lower()
            score = 0
            # Points for artist name in the result title.
            if artist.lower() in rt:
                score += 20
            # Points for each title word that appears.
            for word in title.lower().split():
                if len(word) > 2 and word in rt:
                    score += 5
            # Bonus if the title appears as a phrase.
            if title.lower() in rt:
                score += 15
            if score > best_score:
                best_score = score
                best_result = r

        if not best_result or best_score < 8:
            return None

        # Step 4: Get available qualities from the song page.
        urls = self.get_download_urls(best_result["url"])
        if not urls:
            return None

        # Step 5: Return the best quality found.
        for label in ("320", "256", "128"):
            if label in urls:
                return SourceQuality(label, urls[label], int(label))
        for label, url in urls.items():
            return SourceQuality(label, url, 0)

        return None
