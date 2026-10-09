"""
provider_secondary.py — Alternative audio source provider.

This module serves as the backup source when the primary provider cannot
deliver the requested song or quality. It uses a widely-available streaming
platform as its backend.

Audio from this source is always converted to high-quality MP3 (320 kbps)
for consistency. The original format varies (typically Opus 160-192 kbps
or AAC 128-256 kbps) and is transcoded to ensure uniform quality across
all songs in your library.

Note to contributors:
    The conversion process is lossy-by-lossy, but at 320 kbps the
    difference is inaudible to the vast majority of listeners.
    Audiophiles are welcome to submit a lossless pipeline if they
    can find a source that offers one.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

from soniq.diagnostics import get as diag
from soniq import procutil
from soniq.fsutil import ensure_output_dir, sanitize_filename


# -- Player clients ----------------------------------------------------------
# Client selection synced from Sonic (verified live 2026-08-23):
#   tv_embedded — ONLY client returning URL'd audio (249/250/251/140) while
#                 YouTube's SABR-only experiment strips android audio URLs
#                 (yt-dlp issue #12482). Used FIRST.
#   android,--web;default — worked for SEARCH; also un-SABR'd on videos
#                 not in the experiment.
#   default     — last-resort fallback (48k-only formats, 403-prone).
# NEVER merge clients in one string: the first client returning ANY formats
# wins and masks better clients (verified 2026-08-23). Probe sequentially.
TV_EMBEDDED_ARGS = ["--extractor-args", "youtube:player_client=tv_embedded"]
SEARCH_CLIENT_ARGS = ["--extractor-args", "youtube:player_client=android,--web;default"]
CLIENT_ORDER = (TV_EMBEDDED_ARGS, SEARCH_CLIENT_ARGS, [])


def _norm(s: str) -> str:
    """Normalize for matching: lowercase, strip diacritics/punctuation."""
    import unicodedata
    return "".join(
        c for c in unicodedata.normalize("NFKD", s.lower())
        if c.isalnum() or c.isspace()
    )


def _candidate_score(cand_title: str, artist: str, title: str) -> int:
    """Score how well a YouTube title matches the requested song.

    Synced from Sonic (verified live 2026-08-23): >= 2 = plausible match
    (title phrase +2 or all title words +1, plus the artist token +1).
    Picks the RIGHT video instead of the most-viewed one.
    """
    c = _norm(cand_title)
    t = _norm(title)
    a = _norm(artist)
    if not t:
        return 0
    score = 0
    if t in c:
        score += 2
    else:
        words = [w for w in t.split() if len(w) > 2]
        if words and all(w in c for w in words):
            score += 1
    if a and a in c:
        score += 1
    elif a:
        aw = [w for w in a.split() if len(w) > 2]
        if aw and all(w in c for w in aw):
            score += 1
    return score


# -- Quality Descriptor ------------------------------------------------------

class FallbackQuality:
    """
    Represents a quality option from the fallback source.

    Attributes:
        label:     Quality label, e.g. "opus_192", "m4a_256"
        bitrate:   Bitrate in kbps
        is_opus:   Whether the original format is Opus
        filesize:  Estimated download size in bytes
    """

    TIERS = {
        "opus_192": 4, "opus_160": 3, "opus_128": 2,
        "m4a_256": 3, "m4a_128": 2,
        "opus_96": 1, "opus_64": 1,
    }

    def __init__(self, label: str, format_id: str, bitrate: int = 0,
                 filesize: int = 0, is_opus: bool = True):
        self.label = label
        self.format_id = format_id
        self.bitrate = bitrate
        self.filesize = filesize
        self.is_opus = is_opus

    @property
    def tier(self) -> int:
        """Higher number = better quality within this source."""
        return self.TIERS.get(self.label, 0)

    def __lt__(self, other: "FallbackQuality") -> bool:
        return self.tier < other.tier


# -- Fallback Source Provider ------------------------------------------------

class FallbackProvider:
    """
    Alternative music source used when the primary provider is unavailable
    or does not have the requested song.

    This provider:
      1. Searches for the song on a streaming platform
      2. Selects the best available audio stream
      3. Downloads and converts it to 320 kbps MP3
      4. Strips all source-identifying metadata from the file

    The final output is indistinguishable from the primary source to
    the end user. They do not need to know where it came from.
    """

    def __init__(self, converter_path: str = "yt-dlp"):
        self.converter_path = converter_path
        self._last_best: Optional[dict] = None

    def _is_installed(self) -> bool:
        """Check whether the external converter tool is available on this system."""
        try:
            subprocess.run([self.converter_path, "--version"],
                           capture_output=True, timeout=10)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    # -- Search ----------------------------------------------------------

    def search(self, artist: str, title: str, max_results: int = 10) -> list[dict]:
        """
        Search the fallback source, returning raw relevance-ordered results.

        Fast flat search only (no per-video probes — ranking happens in
        ``find_best`` for the top survivors). Each dict has:
        id, title, url, channel, duration.

        Args:
            artist:      Artist name
            title:       Song title
            max_results: Maximum number of results to fetch

        Returns:
            List of candidate dicts in YouTube relevance order.
        """
        if not self._is_installed():
            diag().add_step("fallback_search", "failed",
                            error_code="ERR_YT_001",
                            error_message="Converter tool not found. "
                                          "Install yt-dlp to enable this source.")
            return []

        query = f"{artist} {title}"
        # Different configurations can return different result sets, so run
        # two of them and merge the results (deduplicate by video id).
        candidates = []
        seen_ids = set()
        last_err = ""
        for attempt_args in (SEARCH_CLIENT_ARGS, []):
            try:
                result = subprocess.run(
                    [self.converter_path, "--flat-playlist", "-J",
                     *attempt_args,
                     f"ytsearch{max_results}:{query}"],
                    capture_output=True, text=True, timeout=30
                )
                if result.returncode != 0:
                    last_err = result.stderr[:200]
                    continue

                data = json.loads(result.stdout)
                for e in data.get("entries", []):
                    vid = e.get("id", "")
                    if not vid or vid in seen_ids:
                        continue
                    seen_ids.add(vid)
                    candidates.append({
                        "id": vid,
                        "title": e.get("title", ""),
                        "url": f"https://youtube.com/watch?v={vid}",
                        "channel": e.get("channel", ""),
                        "duration": e.get("duration", 0),
                        "views": 0,
                    })
            except json.JSONDecodeError as e:
                last_err = f"non-JSON response: {e}"
            except subprocess.TimeoutExpired:
                last_err = "timeout"
            except FileNotFoundError:
                diag().add_step("fallback_search", "failed",
                                error_code="ERR_YT_001")
                return []
            except Exception as e:
                last_err = str(e)

        if not candidates and last_err:
            diag().add_step("fallback_search", "failed",
                            error_code="ERR_YT_002",
                            error_message=str(last_err)[:200])
        return candidates

    # -- Smart pick ------------------------------------------------------

    def find_best(self, artist: str, title: str,
                  max_results: int = 10) -> Optional[dict]:
        """
        Search + match + quality-probe, returning the best audio candidate.

        Match algorithm synced from Sonic (verified live 2026-08-23):
        score every search result against the request — title phrase +2,
        all title words +1, artist token +1 — and keep the best MATCH,
        not the most-viewed. Best score below 2 = nothing matched; fail
        honestly instead of downloading the wrong video.

        Returns a dict with url, title, channel, duration, abr, quality,
        quality_label, score and reasons — or None if nothing acceptable.
        """
        entries = self.search(artist, title, max_results=max_results)
        if not entries:
            diag().add_step(
                "fallback_match", "failed", error_code="ERR_YT_002",
                error_message="Search returned no candidates")
            return None

        scored = sorted(
            ((_candidate_score(e.get("title", ""), artist, title), e)
             for e in entries),
            key=lambda x: x[0], reverse=True,
        )
        best_score, chosen = scored[0]
        if best_score < 2:
            diag().add_step(
                "fallback_match", "failed", error_code="ERR_YT_006",
                error_message=("No search result matches the requested "
                               "artist/title"),
                details={"results": len(entries),
                         "titles": [e.get("title", "")[:80]
                                    for e in entries[:6]]})
            return None

        diag().add_step("fallback_match", "ok",
                        details={"score": best_score,
                                 "picked": chosen.get("title", "")[:80],
                                 "candidates": len(entries)})

        # Probe the matched video for its audio ladder (client ladder:
        # tv_embedded first — Sonic's verified 403/48k fix).
        formats = self.list_qualities(chosen["url"])
        if not formats:
            diag().add_step(
                "fallback_quality", "failed", error_code="ERR_YT_004",
                error_message=("No playable audio stream found for the "
                               "matched video"))
            return None

        quality = formats[0]
        result = {
            "url": chosen["url"],
            "title": chosen.get("title", ""),
            "channel": chosen.get("channel", ""),
            "views": 0,
            "duration": chosen.get("duration", 0),
            "abr": quality.bitrate,
            "quality": quality,      # consumed by best_quality()
            "quality_label": quality.label,
            "score": best_score,
            "reasons": [f"match+{best_score}"],
        }
        result["query_artist"] = artist
        result["query_title"] = title
        self._last_best = result
        return result

    # -- Best Quality Detection ------------------------------------------

    def list_qualities(self, video_url: str) -> list[FallbackQuality]:
        """
        List all available audio formats for a given video URL.

        Returns formats sorted from best to worst quality.
        """
        # Probe clients one at a time — the first client that yields usable
        # audio wins (some clients hide download URLs or expose only the
        # lowest-bitrate stream).
        for client_args in CLIENT_ORDER:
            try:
                result = subprocess.run(
                    [self.converter_path, "-J", "--format-sort", "abr",
                     *client_args, video_url],
                    capture_output=True, text=True, timeout=30
                )
                if result.returncode != 0:
                    continue

                data = json.loads(result.stdout)
                formats = data.get("formats", [])
                qualities = []

                for fmt in formats:
                    acodec = fmt.get("acodec", "")
                    abr = fmt.get("abr", 0)
                    ext = fmt.get("ext", "")
                    format_id = fmt.get("format_id", "")
                    filesize = fmt.get("filesize", 0) or fmt.get("filesize_approx", 0)

                    if acodec == "none" or abr == 0:
                        continue
                    if not fmt.get("url"):
                        # Format advertised without a download URL — skip it.
                        continue

                    is_opus = ext == "webm" and "opus" in acodec
                    if is_opus:
                        qualities.append(FallbackQuality(
                            f"opus_{int(abr)}", format_id, int(abr),
                            filesize, is_opus=True
                        ))
                    elif ext == "m4a":
                        qualities.append(FallbackQuality(
                            f"m4a_{int(abr)}", format_id, int(abr),
                            filesize, is_opus=False
                        ))

                if qualities:
                    qualities.sort(reverse=True)
                    return qualities
            except (json.JSONDecodeError, subprocess.TimeoutExpired):
                continue
        return []

    def best_quality(self, artist: str, title: str) -> Optional[FallbackQuality]:
        """Find the best quality available for a song on the fallback source."""
        best = self.find_best(artist, title)
        if not best or not best.get("quality"):
            return None
        return best["quality"]

    # -- Download & Convert ----------------------------------------------

    def download(self, artist: str, title: str, output_dir: str) -> Optional[str]:
        """
        Download a song and convert it to 320 kbps MP3.

        The best candidate is picked via ``find_best`` (ranked search) and
        downloaded directly by URL — no more yt-dlp's own "first relevance
        hit" (which is usually the official music video).

        Args:
            artist:     Artist name
            title:      Song title
            output_dir: Directory to save the MP3 file

        Returns:
            Path to the converted MP3 file, or None on failure.
        """
        if not self._is_installed():
            diag().add_step("fallback_download", "failed",
                            error_code="ERR_YT_001")
            return None

        best = self.find_best(artist, title)
        if not best or not best.get("url"):
            diag().add_step("fallback_download", "failed",
                            error_code="ERR_YT_006",
                            error_message="No acceptable audio candidate found.")
            return None

        diag().add_step("fallback_download", "in_progress",
                        details={"picked": best.get("title"),
                                 "channel": best.get("channel"),
                                 "score": best.get("score")})
        return self.download_url(best["url"], output_dir,
                                 base_name=f"{artist} - {title}")

    # -- Playlist --------------------------------------------------------

    def list_playlist(self, url: str) -> list[dict]:
        """
        Flat-resolve a YouTube playlist into entry dicts.

        Skips items whose duration is unknown-short (<60s, likely Shorts)
        or very long (>600s, likely compilations). Each entry has:
        id, title, url, duration.

        Args:
            url: The YouTube playlist URL

        Returns:
            List of entry dicts, or [] on failure.
        """
        if not self._is_installed():
            return []
        try:
            result = subprocess.run(
                [self.converter_path, "--flat-playlist", "-J",
                 "--no-warnings", url],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode != 0:
                diag().add_step("playlist_resolve", "failed",
                                error_code="ERR_YT_002",
                                error_message=result.stderr[:200])
                return []
            data = json.loads(result.stdout)
            entries = []
            for e in data.get("entries", []):
                vid = e.get("id", "")
                if not vid:
                    continue
                dur = e.get("duration") or 0
                if dur and (dur < 60 or dur > 600):
                    continue
                entries.append({
                    "id": vid,
                    "title": e.get("title", ""),
                    "url": f"https://youtube.com/watch?v={vid}",
                    "duration": dur,
                })
            return entries
        except (json.JSONDecodeError, subprocess.TimeoutExpired):
            return []
        except Exception:
            return []

    def download_url(self, url: str, output_dir: str,
                     base_name: Optional[str] = None) -> Optional[str]:
        """
        Download a specific YouTube URL and convert it to 320 kbps MP3.

        Used by the ``url`` and ``playlist`` commands (exact URL, no search).
        If base_name is None, the video's own title is used for the filename.

        Args:
            url:        The YouTube watch/playlist URL to download
            output_dir: Directory to save the MP3 file
            base_name:  Optional base name for the output file

        Returns:
            Path to the converted MP3 file, or None on failure.
        """
        if not self._is_installed():
            diag().add_step("fallback_download", "failed",
                            error_code="ERR_YT_001")
            return None

        output_dir = ensure_output_dir(output_dir)
        if base_name:
            safe_name = sanitize_filename(base_name)
        else:
            safe_name = "download"
        output_template = os.path.join(output_dir, f"{safe_name}.%(ext)s")
        final_path = os.path.join(output_dir, f"{safe_name}.mp3")

        # If the file already exists, skip the download.
        if os.path.exists(final_path):
            print("  (already downloaded - skipping)")
            return final_path

        # Probe clients one at a time — the first client that completes a
        # download wins. The tiered selector prefers m4a/opus audio; the
        # default client alone may expose only its low-bitrate stream.
        last_error = ""
        last_code = "ERR_YT_003"
        attempts = []
        for client_args in CLIENT_ORDER:
            client_name = ("default" if not client_args
                           else client_args[1].split("=", 1)[-1])
            try:
                cmd = [
                    self.converter_path,
                    "-f", "bestaudio[ext=m4a]/bestaudio[ext=opus]/bestaudio/best",
                    *client_args,
                    "--extract-audio",
                    "--audio-format", "mp3",
                    "--audio-quality", "0",        # 0 = best (320k)
                    "--embed-metadata",
                    "--embed-thumbnail",
                    "--add-metadata",
                    "-o", output_template,
                    "--no-playlist",
                    "--print", "after_move:filepath",
                    "--no-warnings",
                    url,
                ]

                result = procutil.run_cmd(cmd, timeout=300)

                if result.returncode != 0:
                    last_code = "ERR_YT_003"
                    last_error = result.stdout[-300:]
                    attempts.append((client_name,
                                     result.stdout.strip()[-160:]))
                    if procutil.cancel_requested():
                        diag().add_step(
                            "fallback_download", "failed",
                            error_code="ERR_GEN_003",
                            error_message="Download cancelled.")
                        return None
                    continue

                # Find the output file from the converter's stdout.
                for line in result.stdout.strip().split("\n"):
                    line = line.strip()
                    if line.endswith(".mp3") and os.path.exists(line):
                        return line

                # Fallback: search the output directory.
                for f in os.listdir(output_dir):
                    if f.endswith(".mp3") and (safe_name.lower() in f.lower()
                                               or url[-11:] in f):
                        return os.path.join(output_dir, f)

                last_code = "ERR_YT_005"
                last_error = "download finished but output file not found"
                attempts.append((client_name, "output file not found"))
            except subprocess.TimeoutExpired:
                last_code = "ERR_GEN_002"
                last_error = "timeout"
                attempts.append((client_name, "timeout"))
                continue
            except FileNotFoundError:
                diag().add_step("fallback_download", "failed",
                                error_code="ERR_YT_001")
                return None
            except Exception as e:
                last_code = "ERR_YT_003"
                last_error = str(e)
                attempts.append((client_name, str(e)[:160]))
                continue

        diag().add_step("fallback_download", "failed",
                        error_code=last_code,
                        error_message=last_error or "All player clients failed",
                        details={"attempts": [f"{name}: {err}"
                                              for name, err in attempts]})
        return None
