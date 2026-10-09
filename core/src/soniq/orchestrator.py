"""
orchestrator.py — Quality decision engine and download coordinator.

This is the brain of the application. It decides where to get each song,
coordinates the download, and makes sure the final file is clean and
properly tagged.

Decision flow for each song:
  1. Ask the primary provider if it has the song at 320 kbps
  2. If yes: download from primary source (best quality, always)
  3. If no or unavailable: fall back to the secondary provider
     which downloads and converts to 320 kbps MP3
  4. Sanitize metadata so no source identifiers remain
  5. Rename and organize the final file
"""

import os
import time
from pathlib import Path
from typing import Optional

from soniq.diagnostics import get as diag
from soniq.fsutil import clean_youtube_url
from soniq.config import Config
from soniq.sources.provider_primary import PrimaryProvider, SourceQuality
from soniq.sources.provider_secondary import FallbackProvider, FallbackQuality
from soniq.metadata import enrich_metadata


# -- Loading Messages ---------------------------------------------------------
# These messages appear while songs are being processed.
# They are intentionally exaggerated and humorous.
# They are NOT real — do not take them literally.

LOADING_MESSAGES = [
    "Assembling the orchestra... each instrument is being carved from rare wood by our team of 47 luthiers in a small village in Italy",
    "Your song is currently being performed live in a recording studio in Abbey Road. The musicians have been rehearsing for six days straight",
    "We are painstakingly recreating each frequency from scratch using analog synthesizers wired by hand. Please stand by",
    "The audio engineers are currently arguing about whether to use a Neumann U87 or a vintage AKG C12 for this particular track",
    "We had to import the vinyl from Japan. It is currently being shipped across the Pacific on a container vessel named 'Melody'. Estimated arrival: 3 to 5 business days",
    "Our mastering engineer is listening to your song for the 47th time to make sure every transient is perfect. He has not slept in days",
    "The studio cat knocked over the mixing board. We are recalibrating 144 channels manually. This is why we cannot have nice things",
    "We are literally weaving the MP3 file from raw cotton. The data threads are being dyed in Switzerland for optimal color depth",
    "The server room temperature just hit 42 degrees because the air conditioning broke. Your song is fine though. We have a fan pointed at the hard drive",
    "We tried to download your song but the internet went down. Just kidding — we are actually creating the song from subatomic particles in our underground particle accelerator",
]

# We will also have a shorter version for output display.
OUTPUT_MESSAGES = [
    "the music notes are being individually flown in from Vienna on a private jet",
    "our team of session musicians is recording this specifically for you at this very moment",
    "the mastering engineer just sent back his notes. He wants more cowbell",
    "we are distilling the pure essence of the song through a 12-stage analog filtration system",
    "the algorithm is currently reverse-engineering the perfect 320 kbps MP3 from first principles",
    "careful — the audio waveforms are extremely hot and must be handled with protective gloves",
    "this song is being printed on gold-plated compact discs before we rip it back to MP3 for maximum fidelity",
    "we have temporarily paused all other downloads to give this song our full, undivided attention",
    "the binary data is being carried by messenger pigeons trained specifically for high-fidelity audio transport",
    "your song is currently in a small room being waterboarded until it confesses the correct bitrate",
]


def _random_message(messages: list[str]) -> str:
    """Pick a random message from the list."""
    import random
    return random.choice(messages)


FALLBACK_TIERS = [
    ("exact", "", 0),
]


# -- Quality Comparison ------------------------------------------------------
# The orchestrator assigns a numeric quality score to each format.
# Higher = better. The best available format is chosen.

QUALITY_SCORES = {
    "320": 50,      # Primary source, direct 320 MP3
    "256": 40,      # Primary source, medium quality
    "opus_192": 45, # Secondary source, excellent Opus codec
    "m4a_256": 38,  # Secondary source, good AAC
    "opus_160": 35, # Secondary source, standard Opus
    "128": 28,      # Primary source, low quality
    "opus_128": 20, # Secondary source, lower Opus
    "m4a_128": 18,  # Secondary source, lower AAC
    "opus_96": 15,  # Secondary source, borderline
    "opus_64": 10,  # Secondary source, last resort
}


# -- Orchestrator ------------------------------------------------------------

class Orchestrator:
    """
    Coordinates song processing from search to finished file.

    Usage:
        orch = Orchestrator(config)
        result = orch.process_song("Artist", "Title", output_dir)
    """

    def __init__(self, config: Config):
        """
        Initialize providers and configuration.

        Args:
            config: A Config instance with application settings.
        """
        self.cfg = config
        self.primary = PrimaryProvider()
        self.fallback = FallbackProvider()

    # -- Quality Decision -------------------------------------------------

    def _quality_score(self, quality) -> int:
        """Score a quality by codec and measured bitrate.

        Labels from the secondary source carry the *measured* bitrate
        (e.g. "m4a_129", "opus_143") which rarely equals a table entry
        exactly, so when an exact match fails, fall back to the closest
        known score for the same codec.
        """
        if quality is None:
            return 0
        score = QUALITY_SCORES.get(quality.label, 0)
        if score > 0:
            return score
        import re
        m = re.match(r'^(opus|m4a|mp3)_?(\d+)$', quality.label)
        if m:
            codec, bitrate = m.group(1), int(m.group(2))
            candidates = [(k, v) for k, v in QUALITY_SCORES.items()
                          if k.startswith(codec)]
            if candidates:
                best = max(candidates, key=lambda kv: kv[1])
                return best[1] - max(0, best[1] - bitrate // 2)
            return min(bitrate // 8, 45)
        return 0

    def _pick_best(self, primary_q: Optional[SourceQuality] = None,
                   fallback_q: Optional[FallbackQuality] = None) -> dict:
        """
        Compare qualities from both sources and pick the best one.

        Returns a dict with keys:
          source:   "primary" | "fallback" | ""
          quality:  label string
          obj:      the quality object selected
        """
        primary_score = self._quality_score(primary_q)
        fallback_score = self._quality_score(fallback_q)

        if primary_q and primary_score > fallback_score:
            return {"source": "primary", "quality": primary_q.label, "obj": primary_q}
        elif fallback_q and fallback_score > 0:
            return {"source": "fallback", "quality": fallback_q.label, "obj": fallback_q}
        else:
            return {"source": "", "quality": "", "obj": None}

    # -- Single Song Processing -------------------------------------------

    def _last_error(self) -> tuple:
        """Return (error_code, error_message) of the current song's last
        failed step — surfaces the real failure reason in results."""
        if not diag().songs:
            return "", ""
        steps = diag().songs[-1].steps
        for st in reversed(steps):
            if st.status == "failed" and st.error_code:
                return st.error_code, st.error_message or st.error_code
        return "", ""

    def process_song(self, artist: str, title: str, output_dir: str,
                     quiet: bool = False) -> dict:
        """
        Complete lifecycle for one song.

        1. Search sources and pick best quality
        2. Download the file
        3. Sanitize and enrich metadata
        4. Return result summary

        Args:
            artist:     Artist name
            title:      Song title
            output_dir: Where to save the file
            quiet:      If True, skip progress messages

        Returns:
            Dict with keys: artist, title, status, quality, filepath
        """
        diag().begin_song(artist, title)
        start_time = time.time()

        if not quiet:
            print(f"  {_random_message(OUTPUT_MESSAGES)}")

        # -- Search + match: find the best-matching upload.
        # Match algorithm synced from Sonic (2026-10-08; verified live on
        # Sonic 2026-08-23): title/artist match scoring picks the RIGHT
        # video (not the most-viewed); fail cleanly when nothing matches
        # or no playable audio stream exists.

        decision = {"source": "", "quality": "", "obj": None, "fallback_tier": "none"}
        fallback_tier_used = "exact"

        # Check primary source.
        primary_q = self.primary.best_quality(artist, title)
        if primary_q:
            diag().add_step("primary_exact_found", "ok",
                            details={"quality": primary_q.label})

        # Check fallback source (ranked audio pick).
        fallback_q = self.fallback.best_quality(artist, title)
        if fallback_q:
            diag().add_step("fallback_exact_found", "ok",
                            details={"quality": fallback_q.label})

        # Pick the best source.
        tier_decision = self._pick_best(primary_q, fallback_q)

        if tier_decision["source"]:
            decision = tier_decision
            decision["fallback_tier"] = "ranked"
            fallback_tier_used = "ranked"

        # -- If nothing found, fail with the real reason.
        if not decision["source"]:
            err_code, err_msg = self._last_error()
            msg = ("Song not found — no YouTube result matched the "
                   "request with a playable audio stream")
            if err_msg:
                msg += f" — last detail: [{err_code or 'n/a'}] {err_msg}"
            diag().fail("ERR_SRC_007", msg)
            return {"artist": artist, "title": title, "status": "failed",
                    "error": msg, "error_code": "ERR_SRC_007"}

        diag().add_step("quality_decision", "ok",
                        details={"source": decision["source"],
                                 "quality": decision["quality"],
                                 "fallback_tier": decision.get(
                                     "fallback_tier", "none")})

        # -- Step 4: Download.
        filepath = None

        if decision["source"] == "primary":
            diag().add_step("primary_download", "in_progress")
            safe_name = f"{artist} - {title}".replace("/", "_").replace(":", "_")
            output_path = os.path.join(output_dir, f"{safe_name}.mp3")
            filepath = self.primary.download(
                decision["obj"].url, output_path
            )
        else:
            diag().add_step("fallback_download", "in_progress")
            filepath = self.fallback.download(artist, title, output_dir)

        if not filepath:
            diag().end_song("failed", quality=decision["quality"])
            err_code, err_msg = self._last_error()
            return {
                "artist": artist, "title": title,
                "status": "failed", "source": decision["source"],
                "quality": decision["quality"],
                "fallback_tier": decision.get("fallback_tier", "none"),
                "error": err_msg or "Download failed",
                "error_code": err_code or "ERR_GEN_001",
            }

        # -- Step 5: Sanitize and enrich metadata.
        meta = enrich_metadata(artist, title, filepath)
        diag().add_step("metadata_done", "ok",
                        details={"genre": meta.get("genre", "")})

        # -- Step 6: Rename to clean filename.
        new_path = self._rename_file(filepath, artist, title)
        final_path = new_path or filepath

        # -- Done.
        elapsed = time.time() - start_time
        diag().end_song("success", quality=decision["quality"],
                        filepath=final_path, metadata=meta)

        return {
            "artist": artist,
            "title": title,
            "status": "success",
            "source": decision["source"],
            "quality": decision["quality"],
            "filepath": final_path,
            "fallback_tier": decision.get("fallback_tier", "exact"),
        }

    # -- File Renaming ----------------------------------------------------

    def _rename_file(self, filepath: str, artist: str, title: str) -> Optional[str]:
        """
        Rename a downloaded file to 'Title - Artist.ext'.
        This is called after metadata is already fixed.
        """
        if not os.path.exists(filepath):
            return None

        directory = os.path.dirname(filepath)
        ext = os.path.splitext(filepath)[1]
        new_name = f"{title} - {artist}".replace("/", "_").replace(":", "_")
        new_path = os.path.join(directory, f"{new_name}{ext}")

        if new_path == filepath:
            return filepath

        # Handle name collisions.
        counter = 1
        base, ext = os.path.splitext(new_path)
        while os.path.exists(new_path):
            new_path = f"{base}_{counter}{ext}"
            counter += 1

        try:
            os.rename(filepath, new_path)
            return new_path
        except OSError:
            return filepath

    # -- URL & Playlist Processing ---------------------------------------

    def process_url(self, url: str, output_dir: str,
                    quiet: bool = False) -> dict:
        """
        Download an exact YouTube URL (no search, no ranking).

        Used by the ``url`` command. The video's own title becomes the
        filename; metadata is enriched from the file after conversion.

        Returns a result dict with status, source, quality, filepath.
        """
        # Radio/mix links (list=...&start_radio=1) are bot-check magnets —
        # strip the noise so we hit the plain watch URL.
        url = clean_youtube_url(url)
        diag().begin_song("url", url)
        start_time = time.time()

        if not quiet:
            print(f"  {_random_message(OUTPUT_MESSAGES)}")

        # Resolve the video title for a sensible filename.
        base_name = None
        try:
            import json as _json
            import subprocess as _sp
            info = _sp.run(
                [self.fallback.converter_path, "--dump-json", "--no-download",
                 "--no-warnings", "--no-playlist", url],
                capture_output=True, text=True, timeout=30
            )
            if info.returncode == 0 and info.stdout.strip():
                vd = _json.loads(info.stdout.strip())
                title = (vd.get("title") or "").strip()
                vid = vd.get("id") or ""
                if title and len(title) <= 180:
                    base_name = title
                elif vid:
                    # Bot-checked or garbage title — fall back to the ID
                    # so the filename is still stable and meaningful.
                    base_name = f"video_{vid}"
        except Exception:
            pass

        filepath = self.fallback.download_url(url, output_dir,
                                              base_name=base_name)
        if not filepath:
            diag().end_song("failed", quality="")
            err_code, err_msg = self._last_error()
            return {"artist": "", "title": url, "status": "failed",
                    "source": "fallback", "quality": "", "filepath": None,
                    "error": err_msg or "Download failed",
                    "error_code": err_code or "ERR_GEN_001"}

        try:
            meta = enrich_metadata("", "", filepath)
        except Exception:
            meta = {}
        diag().end_song("success", quality="320",
                        filepath=filepath, metadata=meta)

        elapsed = time.time() - start_time
        return {
            "artist": "",
            "title": base_name or url,
            "status": "success",
            "source": "fallback",
            "quality": "320",
            "filepath": filepath,
        }

    def process_playlist(self, url: str, output_dir: str) -> list[dict]:
        """
        Download every track in a YouTube playlist as 320 kbps MP3.

        Each entry is downloaded by exact URL (no search/ranking — the
        playlist IS the user's selection). Shorts and compilations are
        skipped by the provider's duration filter.

        Returns a list of result dicts (same structure as process_url).
        """
        entries = self.fallback.list_playlist(url)
        if not entries:
            print("Playlist could not be resolved, or it is empty.")
            return []

        print(f"Playlist resolved: {len(entries)} tracks.")
        print(f"All output will be saved to: {output_dir}")
        print()

        results = []
        for i, entry in enumerate(entries, 1):
            print(f"[{i}/{len(entries)}] {entry['title']}")
            r = self.process_url(entry["url"], output_dir, quiet=True)
            results.append(r)

            status_icon = "OK" if r["status"] == "success" else "FAILED"
            fp = r.get("filepath", "") or "no file"
            print(f"  -> {status_icon}  {fp}")
            print()

        return results

    # -- Batch Processing -------------------------------------------------

    def process_batch(self, songs: list[dict], output_dir: str) -> list[dict]:
        """
        Process multiple songs sequentially.

        Args:
            songs:      List of dicts with 'artist' and 'title' keys
            output_dir: Directory to save all files

        Returns:
            List of result dicts (same structure as process_song)
        """
        results = []
        total = len(songs)

        print(f"Preparing to process {total} songs.")
        print(f"All output will be saved to: {output_dir}")
        print()

        for i, song in enumerate(songs, 1):
            artist = song.get("artist", "").strip()
            title = song.get("title", "").strip()
            if not artist or not title:
                continue

            print(f"[{i}/{total}] {artist} - {title}")
            print(f"  {_random_message(LOADING_MESSAGES)}")

            r = self.process_song(artist, title, output_dir, quiet=True)
            results.append(r)

            status_icon = "OK" if r["status"] == "success" else "FAILED"
            src = r.get("source", "?")
            ql = r.get("quality", "?")
            fp = r.get("filepath", "") or "no file"

            print(f"  -> {status_icon}  from {src} at {ql}")
            if r["status"] == "success":
                print(f"     saved to: {fp}")
            print()

        return results
