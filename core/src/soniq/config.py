"""
config.py — Application configuration management.

Settings are stored in ~/.soniq/config.json as simple key-value pairs.
If the file does not exist, sensible defaults are used automatically.

Configuration file structure:
{
    "output_dir": "~/Music/SoniQ",
    "keep_original_files": false,
    "preferred_language": "en"
}
"""

import json
import os
from pathlib import Path
from typing import Any, Optional

from soniq.diagnostics import get as diag


# -- Default Settings --------------------------------------------------------
# These are used when the user has not created a config file yet.

DEFAULT_CONFIG = {
    "output_dir": str(Path.home() / "Music" / "SoniQ"),
    "output_dir_chosen": False,
    "check_for_updates": True,
    "keep_original_files": False,
    "preferred_language": "en",
    "max_concurrent_downloads": 3,
    "always_high_quality": True,
    # Source endpoints — these are where the application queries for music.
    # Change them only if you know what you are doing.
    "primary_source_url": "https://musics-fa.com",
    "primary_source_cdn": "https://dls.musics-fa.com",
    "secondary_source_enabled": True,
    "secondary_source_search_url": "https://youtube.com/watch?v={id}",
    "secondary_source_query_prefix": "ytsearch",
}


# -- Config Loader -----------------------------------------------------------

class Config:
    """
    Handles loading, merging, and accessing configuration values.

    The config file is optional. When it does not exist, defaults are used
    and a new file is created automatically on first run.

    Usage:
        cfg = Config()
        output_dir = cfg.get("output_dir")
        profile_name = cfg.get("profile", "name")
    """

    def __init__(self, config_path: str = ""):
        """
        Initialize configuration from a JSON file.

        Args:
            config_path: Full path to the config file. If empty, uses
                         ~/.soniq/config.json by default.
        """
        self._data: dict[str, Any] = {}
        self._path = config_path or os.environ.get(
            "SONIQ_CONFIG",
            str(Path.home() / ".soniq" / "config.json")
        )
        self._load()

    def _load(self):
        """
        Read config from disk and merge with defaults.

        Defaults act as a safety net — if a setting is missing from the
        user's file, the default value is used instead of crashing.
        """
        self._data = dict(DEFAULT_CONFIG)

        path = Path(self._path)
        if path.exists():
            try:
                with open(path) as f:
                    user_config = json.load(f)
                # Merge user values on top of defaults
                for key, value in user_config.items():
                    self._data[key] = value
            except (json.JSONDecodeError, OSError) as e:
                diag().add_step("config_load", "failed",
                                error_code="ERR_CFG_001",
                                error_message=str(e))
        else:
            # No config file yet — write defaults so the user can edit them
            self._write_default()

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by key name."""
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Update a setting and persist the config file.

        Persisting is best-effort: if the write fails, the new value
        still applies for the current session.
        """
        self._data[key] = value
        try:
            path = Path(self._path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    def to_dict(self) -> dict:
        """Return the full config dictionary."""
        return dict(self._data)

    def _write_default(self):
        """Create the default config file at the expected location."""
        try:
            path = Path(self._path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
        except OSError:
            pass  # Non-critical — defaults work in memory
