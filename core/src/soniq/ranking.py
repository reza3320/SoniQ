"""
ranking.py — Search result ranking engine (Reza's pick algorithm).

Picks the RIGHT YouTube upload for a song: the official AUDIO upload, not
the music video, not live, not remix/cover/karaoke.

Two-phase selection:
  Phase 1 (cheap): classify + score all flat search results by title,
                   channel and duration. Hard-exclude video/live/remix/cover.
  Phase 2 (probe): probe the top survivors for real view counts and audio
                   bitrate; the winner is the highest-scoring candidate,
                   with views as the tiebreaker.

Signals (from observed manual selection behavior):
  +3  channel is the artist's own channel (or "Artist - Topic" auto channel)
  +3  channel is a known audio/lyrics aggregator (7clouds, SyrebralVibes, ...)
  +2  "lyrics" / "audio" marker (official-audio signal, NOT a video)
  +3  title token overlap with the requested artist+title (transliteration-
      tolerant: "goriz" ~ "goreez" via longest-common-substring)
  +1  song-like duration (150-420 s)
  -1  translator/subtitle channels (lyrics translations, not the song)
  views: logarithmic tiebreaker only (never the primary signal)
"""

from __future__ import annotations

import math
import re
from typing import Optional

# -- Channel allowlist --------------------------------------------------------
# Known audio/lyrics aggregator channels. These are trusted audio uploads.

KNOWN_AUDIO_CHANNELS = frozenset({
    "7clouds", "7clouds rock", "syrebralvibes", "trap nation", "wavemusic",
    "xpertvibes", "auroravibes", "chill nation", "cloudkid", "ncs",
    "no copyright sounds", "ultra music", "monstercat", "proximity",
    "tasty", "selected", "vibes only", "dejavu", "trapnatio",
    "blacklist", "fearless", "future bass", "wave music", "chillhop",
})

# Normalized form (spaces/punct stripped) for matching against _norm_channel
_KNOWN_AUDIO_NORM = frozenset(
    re.sub(r"[\s\-_'&.]+", "", c) for c in KNOWN_AUDIO_CHANNELS)

# -- Marker regexes -----------------------------------------------------------

_MV_RE = re.compile(
    r"\b(music video|official video|official music video|videoclip|video clip|"
    r"mv|ویدیو|ویدئو|موزیک ویدئو|موزیک ویدیو)\b", re.IGNORECASE)
_LIVE_RE = re.compile(
    r"\b(live|concert|کنسرت|زنده|pinkpop|festival)\b", re.IGNORECASE)
_REMIX_RE = re.compile(
    r"\b(remix|ریمیکس|sped up|slowed|rework|edit)\b", re.IGNORECASE)
_COVER_RE = re.compile(
    r"\b(cover|karaoke|کارائوکه|کاور|instrumental|piano|acoustic|band)\b",
    re.IGNORECASE)
_AUDIO_POS_RE = re.compile(
    r"\b(lyrics|lyric video|audio|official audio)\b", re.IGNORECASE)
_TRANSLATOR_RE = re.compile(
    r"\b(traductor|translation|español|spanish|subtitle)\b", re.IGNORECASE)
_TOPIC_RE = re.compile(r"- topic\s*$", re.IGNORECASE)


# -- Classification -----------------------------------------------------------

def classify(title: str) -> dict:
    """Return flag dict for a video title: mv/live/remix/cover/lyrics/translator."""
    t = title or ""
    return {
        "mv": bool(_MV_RE.search(t)),
        "live": bool(_LIVE_RE.search(t)),
        "remix": bool(_REMIX_RE.search(t)),
        "cover": bool(_COVER_RE.search(t)),
        "lyrics": bool(_AUDIO_POS_RE.search(t)),
        "translator": bool(_TRANSLATOR_RE.search(t)),
    }


def is_excluded(flags: dict) -> bool:
    """Hard exclusions — these are NEVER auto-picked."""
    return bool(flags["mv"] or flags["live"] or flags["remix"] or flags["cover"])


# -- Normalization & matching -------------------------------------------------

_TOKEN_SPLIT_RE = re.compile(r"[^\w]+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_SPLIT_RE.split(text or "") if t]


def _lcs_ratio(a: str, b: str) -> float:
    """Longest common substring length / min length. Transliteration tolerance."""
    a, b = a.lower(), b.lower()
    if not a or not b:
        return 0.0
    # DP over short strings only (title tokens are tiny)
    m, n = len(a), len(b)
    table = [[0] * (n + 1) for _ in range(m + 1)]
    best = 0
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                table[i][j] = table[i - 1][j - 1] + 1
                if table[i][j] > best:
                    best = table[i][j]
    return best / min(m, n)


def _token_matches(q: str, t: str) -> bool:
    """Exact match, or transliteration-tolerance match for latin tokens."""
    if q == t:
        return True
    if not (q.isascii() and t.isascii()):
        return False
    return _lcs_ratio(q, t) >= 0.6


def _norm_channel(channel: str) -> str:
    """Normalize a channel name for matching: lowercase, drop spaces/punct."""
    c = (channel or "").lower().strip()
    c = _TOPIC_RE.sub("", c).strip()
    c = re.sub(r"[\s\-_'&.]+", "", c)
    return c


def _channel_score(channel: str, artist: str, title: str) -> int:
    """+3 artist's own channel (incl. - Topic auto channel) or known aggregator."""
    c = _norm_channel(channel)
    if not c:
        return 0
    is_topic = bool(_TOPIC_RE.search(channel or ""))

    # The user may type "Artist - Title" OR "Title - Artist" — try both segments.
    for name in (artist, title):
        n = _norm_channel(name)
        if n and c == n:
            return 3
    if is_topic:
        # "Navid & Omid - Topic" style: auto-generated official audio channel
        return 2
    if c in _KNOWN_AUDIO_NORM:
        return 3
    if any(k in c for k in ("lyrics", "vibes", "audio")):
        return 1
    return 0


def _title_overlap(title: str, artist: str, title_query: str) -> int:
    """Score 0..3 for how well the video title matches the requested SONG.

    The TITLE-side token is the critical one: a video of a DIFFERENT song
    must not rank high just because it is on the artist's channel. If the
    title token is absent entirely, return -3 (wrong-song penalty).

      title token matched          -> +2  (1 token)
      all title tokens matched     -> +3  (2+ tokens)
      artist token also in title   -> +1  (bonus, max total 3)
    """
    title_tokens = _tokens(title_query)
    if not title_tokens:
        return 0

    title_hit = set()
    for tq in title_tokens:
        for tt in _tokens(title):
            if _token_matches(tq, tt):
                title_hit.add(tq)
                break

    if not title_hit:
        return -3  # wrong song — sink it

    score = 2 if len(title_tokens) == 1 else 3
    # Artist token present in title adds nothing beyond the cap; absent is fine
    # (the channel may carry it, e.g. "Goriz" on channel "EBI").
    return score


# -- Full scoring -------------------------------------------------------------

def score_candidate(candidate: dict, artist: str, title_query: str) -> Optional[dict]:
    """Score one candidate. Returns None if hard-excluded, else a scored dict."""
    flags = classify(candidate.get("title", ""))
    if is_excluded(flags):
        return None

    score = 0.0
    reasons = []

    ch = _channel_score(candidate.get("channel", ""), artist, title_query)
    if ch:
        score += ch
        reasons.append(f"channel+{ch}")

    ov = _title_overlap(candidate.get("title", ""), artist, title_query)
    if ov:
        score += ov
        reasons.append(f"title+{ov}")

    if flags["lyrics"]:
        score += 2
        reasons.append("lyrics+2")
    if flags["translator"]:
        score -= 1
        reasons.append("translator-1")

    dur = candidate.get("duration") or 0
    if 150 <= dur <= 420:
        score += 1
        reasons.append("dur+1")

    views = candidate.get("views") or 0
    if views:
        score += min(math.log10(max(views, 1)) / 20, 0.5)
        reasons.append(f"views{views}")

    return {
        "score": round(score, 3),
        "reasons": reasons,
        "flags": flags,
        "id": candidate.get("id", ""),
        "title": candidate.get("title", ""),
        "channel": candidate.get("channel", ""),
        "url": candidate.get("url", ""),
        "duration": dur,
        "views": views,
    }


def rank_candidates(candidates: list[dict], artist: str, title_query: str) -> list[dict]:
    """Rank all candidates; excluded ones are dropped. Sorted best-first."""
    scored = []
    for c in candidates:
        s = score_candidate(c, artist, title_query)
        if s:
            scored.append(s)
    scored.sort(key=lambda x: (x["score"], x["views"]), reverse=True)
    return scored
