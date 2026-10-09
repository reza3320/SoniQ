#!/bin/bash
# SoniQ launcher - starts the app from this folder.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
python3 -B core/run.py "$@"
