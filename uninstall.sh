#!/bin/bash
# SoniQ uninstaller (macOS / Linux)
#
# Removes the app's shortcuts, launcher and caches. Optionally removes
# your settings and the run logs. Your downloaded music is NEVER touched.
#
# Run from the SoniQ folder:  ./uninstall.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VER=$(cat VERSION 2>/dev/null || echo "?")
echo ""
echo "  SoniQ uninstaller (v$VER)"
echo "  ------------------------------------------"
echo ""

# 1. Shortcuts and helpers
rm -f "$HOME/.local/share/applications/soniq.desktop" 2>/dev/null
rm -rf "$HOME/Applications/SoniQ.app" 2>/dev/null
rm -f "$SCRIPT_DIR/app.sh" 2>/dev/null
rm -f "$HOME/Desktop/soniq.desktop" 2>/dev/null
find "$SCRIPT_DIR" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
echo "  Menu entry / app bundle / launcher / caches removed."

# 2. Settings (optional)
printf "  Also remove your settings (config + diagnostics)? [y/N]: "
read -r answer
case "$answer" in
    y|Y)
        rm -rf "$HOME/.soniq" 2>/dev/null
        echo "  Settings removed."
        ;;
    *)
        echo "  Settings kept."
        ;;
esac

# 3. Logs (optional)
printf "  Also remove the run logs? [y/N]: "
read -r answer
case "$answer" in
    y|Y)
        rm -rf "$SCRIPT_DIR/logs" 2>/dev/null
        echo "  Logs removed."
        ;;
    *)
        echo "  Logs kept."
        ;;
esac

echo ""
echo "  Done. To fully remove SoniQ, delete this folder:"
echo "      $SCRIPT_DIR"
echo "  Your downloaded songs were not touched."
echo ""
