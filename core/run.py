#!/usr/bin/env python3
"""
SoniQ — High-quality music downloader.

Run this script to start.
Usage: python3 run.py download "Artist - Title"
       python3 run.py batch songs.json
"""

import sys
from pathlib import Path

# Add the src directory to the module search path.
src_dir = Path(__file__).resolve().parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

# Delegate to the main module.
from soniq.__main__ import main

main()
