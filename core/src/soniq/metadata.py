"""
metadata.py — Audio metadata cleanup and enrichment.

Every downloaded file goes through this module before it reaches the user.

Two things happen here:
  1. Source-identifying metadata is stripped. No one should see
     filenames, URLs, or comments that reveal where the file came from.
  2. Missing metadata (genre, album art, year) is optionally filled in
     using a public music database lookup.

The goal is a clean, consistent file that looks like it was always yours.
"""

import os
import re
import time
from pathlib import Path
from typing import Optional

from soniq.diagnostics import get as diag


# -- Metadata Sanitization ---------------------------------------------------
# This removes any leftover breadcrumbs from the download process.

def sanitize_metadata(filepath: str, artist: str, title: str):
    """
    Strip all source-identifying information from a downloaded file.

    Many download sources embed their own URLs or branding in metadata
    fields like 'comment', 'publisher', 'encoder', or 'WOAF' (URL).
    This function removes those fields so the file appears clean.

    Args:
        filepath: Path to the audio file
        artist:   Correct artist name
        title:    Correct song title
    """
    if not os.path.exists(filepath):
        return

    ext = Path(filepath).suffix.lower()

    try:
        if ext == ".mp3":
            from mutagen.id3 import ID3, TIT2, TPE1, TCON, TALB, TDRC, COMM, WOAF

            try:
                audio = ID3(filepath)
            except Exception:
                # No existing tags — nothing to sanitize.
                return

            # Remove source-identifying frames.
            for frame_id in ["WOAF", "WOAS", "WOAR", "COMM:eng",
                             "COMM:", "TENC", "TSSE", "WXXX"]:
                if frame_id in audio:
                    del audio[frame_id]

            # Set the core fields to our known-good values.
            audio["TIT2"] = TIT2(encoding=3, text=[title])
            audio["TPE1"] = TPE1(encoding=3, text=[artist])

            # Remove any publisher or copyright that mentions the source.
            for frame_id in ["TPUB", "TCOP"]:
                if frame_id in audio:
                    text = str(audio[frame_id])
                    if any(kw in text.lower() for kw in
                           ["dls.", "musics-fa", ".com", ".ir", "download"]):
                        del audio[frame_id]

            audio.save()

        elif ext == ".flac":
            from mutagen.flac import FLAC

            try:
                audio = FLAC(filepath)
            except Exception:
                return

            # Remove fields that commonly contain source info.
            for key in ["description", "comment", "publisher",
                        "encoded_by", "url", "www"]:
                if key in audio:
                    del audio[key]

            audio["artist"] = artist
            audio["title"] = title
            audio.save()

        elif ext in (".m4a", ".mp4"):
            from mutagen.mp4 import MP4

            try:
                audio = MP4(filepath)
            except Exception:
                return

            # Remove source identifier fields.
            for key in ["\u00a9too", "\u00a9enc", "purd", "\u00a9pub"]:
                if key in audio:
                    del audio[key]

            audio["\u00a9ART"] = artist
            audio["\u00a9nam"] = title
            audio.save()

    except ImportError:
        # Mutagen is optional. Without it, we skip sanitization.
        pass
    except Exception as e:
        diag().add_step("metadata_sanitize", "failed",
                        error_code="ERR_META_003", error_message=str(e))


# -- Music Database Lookup ---------------------------------------------------

class MusicDatabase:
    """
    Public music metadata lookup service.

    Used only to fill in missing information like genre, album, and year.
    The artist and title from the download are always treated as correct.

    Rate limit: 1 request per second (service policy).
    """

    def __init__(self, rate_limit: float = 1.0):
        self.rate_limit = rate_limit
        self._last_request: float = 0

    def _wait(self):
        elapsed = time.time() - self._last_request
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self._last_request = time.time()

    def lookup(self, artist: str, title: str) -> Optional[dict]:
        """
        Search the music database for additional metadata.

        Returns a dict with keys: genre, album, year, tags
        Returns None if no match was found.
        """
        import urllib.request
        import urllib.parse
        import json

        self._wait()

        query = urllib.parse.quote(f'artist:"{artist}" AND recording:"{title}"')
        url = f"https://musicbrainz.org/ws/2/recording/?query={query}&fmt=json&limit=3"

        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "SoniQ/0.1.0 (music downloader)",
                    "Accept": "application/json",
                }
            )
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read().decode())

            recordings = data.get("recordings", [])
            if not recordings:
                return None

            # Pick the recording with the most tags (best match).
            best = max(recordings, key=lambda r: len(r.get("tags", [])))

            return {
                "mbid": best.get("id", ""),
                "title": best.get("title", ""),
                "tags": [t.get("name", "") for t in best.get("tags", [])],
                "releases": [
                    {
                        "title": rel.get("title", ""),
                        "date": rel.get("date", ""),
                    }
                    for rel in best.get("releases", [])[:3]
                ],
            }

        except Exception as e:
            diag().add_step("database_lookup", "failed",
                            error_code="ERR_META_001", error_message=str(e))
            return None

    def infer_genre(self, tags: list[str]) -> str:
        """
        Guess the most specific genre from a list of database tags.

        The database returns community-contributed tags which vary wildly
        in quality. This function maps them to standard genre names.
        """
        genre_map = {
            "pop": "Pop", "rock": "Rock", "hip hop": "Hip-Hop",
            "rap": "Hip-Hop", "jazz": "Jazz", "blues": "Blues",
            "electronic": "Electronic", "dance": "Dance",
            "rnb": "R&B", "soul": "Soul", "classical": "Classical",
            "folk": "Folk", "country": "Country", "metal": "Metal",
            "punk": "Punk", "reggae": "Reggae", "latin": "Latin",
            "indie": "Indie", "alternative": "Alternative",
            "house": "House", "techno": "Techno", "trance": "Trance",
            "dubstep": "Dubstep", "ambient": "Ambient",
        }
        for tag in tags:
            tag_lower = tag.lower()
            for keyword, genre in genre_map.items():
                if keyword in tag_lower:
                    return genre
        return ""


# -- Genre Detection from Context --------------------------------------------

def detect_genre(title: str, channel: str = "") -> str:
    """
    Detect genre from contextual clues in the title or channel name.

    This is used as a first pass before consulting the music database.
    It works well for mainstream music where keywords are common.
    """
    text = f"{title} {channel}".lower()
    patterns = {
        "Deep House":     [r"deep\s*house", r"deep\s+house\s+remix"],
        "Hip-Hop":        [r"\bhip.?hop\b", r"\brap\b", r"trap\b"],
        "Rock":           [r"\brock\b", r"alternative\b", r"indie\s+rock"],
        "Pop":            [r"\bpop\b", r"pop\s+music"],
        "Electronic":     [r"electronic", r"edm", r"dance"],
        "R&B":            [r"\br.?n.?b\b", r"randb"],
        "Jazz":           [r"\bjazz\b"],
        "Classical":      [r"classical", r"orchestra", r"symphony"],
        "Country":        [r"\bcountry\b"],
        "Metal":          [r"\bmetal\b"],
        "Reggae":         [r"reggae", r"dancehall"],
        "Latin":          [r"\blatin\b", r"salsa", r"reggaeton"],
        "Folk":           [r"\bfolk\b", r"acoustic"],
        "Blues":          [r"\bblues\b"],
        "House":          [r"\bhouse\b"],
        "Trance":         [r"\btrance\b"],
    }
    for genre, regexes in patterns.items():
        for regex in regexes:
            if re.search(regex, text):
                return genre
    return ""


# -- Metadata Pipeline -------------------------------------------------------

def enrich_metadata(artist: str, title: str, filepath: str,
                    enable_database: bool = True) -> dict:
    """
    Full metadata pipeline for one downloaded file.

    Steps:
      1. Sanitize — strip any source-identifying metadata
      2. Detect genre from contextual clues
      3. Optionally look up missing info in the music database
      4. Write clean metadata to the file

    Args:
        artist:           Artist name (from the user's request)
        title:            Song title (from the user's request)
        filepath:         Path to the downloaded file
        enable_database:  Whether to consult the external database

    Returns:
        Dict of metadata that was applied: {artist, title, genre, album, year}
    """
    result = {"artist": artist, "title": title, "genre": "", "album": "", "year": ""}

    if not os.path.exists(filepath):
        diag().add_step("metadata_enrich", "failed",
                        error_code="ERR_META_002",
                        error_message=f"File not found: {filepath}")
        return result

    # Step 1: Sanitize (strip source identifiers).
    sanitize_metadata(filepath, artist, title)

    # Step 2: Detect genre from available context.
    # (The file may already have some tags from the download process.)
    genre = detect_genre(f"{artist} {title}")
    if genre:
        result["genre"] = genre

    # Step 3: Optional database lookup for missing fields.
    if enable_database:
        db = MusicDatabase()
        data = db.lookup(artist, title)
        if data:
            # Fill genre from database if not detected above.
            if not result["genre"] and data.get("tags"):
                db_genre = db.infer_genre(data["tags"])
                if db_genre:
                    result["genre"] = db_genre

            # Fill album and year from the first release entry.
            releases = data.get("releases", [])
            if releases:
                if releases[0].get("title"):
                    result["album"] = releases[0]["title"]
                if releases[0].get("date"):
                    result["year"] = releases[0]["date"][:4]

    # Step 4: Write the clean metadata to the file.
    _write_metadata(filepath, result)

    return result


def _write_metadata(filepath: str, meta: dict):
    """
    Write metadata fields to an audio file using mutagen.

    This is called after sanitization and enrichment are complete.
    """
    ext = Path(filepath).suffix.lower()

    try:
        if ext == ".mp3":
            from mutagen.id3 import ID3, TIT2, TPE1, TCON, TALB, TDRC

            try:
                audio = ID3(filepath)
            except Exception:
                return

            if meta.get("title"):
                audio["TIT2"] = TIT2(encoding=3, text=[meta["title"]])
            if meta.get("artist"):
                audio["TPE1"] = TPE1(encoding=3, text=[meta["artist"]])
            if meta.get("genre"):
                audio["TCON"] = TCON(encoding=3, text=[meta["genre"]])
            if meta.get("album"):
                audio["TALB"] = TALB(encoding=3, text=[meta["album"]])
            if meta.get("year"):
                audio["TDRC"] = TDRC(encoding=3, text=[meta["year"]])

            audio.save()

        elif ext == ".flac":
            from mutagen.flac import FLAC

            try:
                audio = FLAC(filepath)
            except Exception:
                return

            for key, val in meta.items():
                if val:
                    audio[key] = val
            audio.save()

        elif ext in (".m4a", ".mp4"):
            from mutagen.mp4 import MP4

            try:
                audio = MP4(filepath)
            except Exception:
                return

            if meta.get("title"):
                audio["\u00a9nam"] = meta["title"]
            if meta.get("artist"):
                audio["\u00a9ART"] = meta["artist"]
            if meta.get("genre"):
                audio["\u00a9gen"] = meta["genre"]
            if meta.get("album"):
                audio["\u00a9alb"] = meta["album"]
            audio.save()

    except ImportError:
        pass  # Mutagen not installed — skip metadata writing.
    except Exception as e:
        diag().add_step("metadata_write", "failed",
                        error_code="ERR_META_003", error_message=str(e))
