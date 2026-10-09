#!/bin/bash
# SoniQ — macOS Installer
# Run this script to install everything needed:
#   chmod +x install.sh
#   ./install.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BOLD='\033[1m'
GREEN='\033[0;32m'
NC='\033[0m'

echo ""
echo "============================================"
echo "   SoniQ — Installation (macOS)"
echo "   v$(cat "$SCRIPT_DIR/VERSION" 2>/dev/null || echo "unknown")"
echo "============================================"
echo ""
if [ -f "$SCRIPT_DIR/app.sh" ]; then
    echo "   Existing installation found — updating in place."
    echo "   Your settings, logs and downloads are preserved."
    echo ""
fi

# ──────────────────────────────────────────────
# Step 1: Check / Install Homebrew
# ──────────────────────────────────────────────
echo "[1/6] Checking Homebrew..."
if ! command -v brew &>/dev/null; then
    echo "  Homebrew is not installed."
    echo "  Installing Homebrew (this may take a few minutes)..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    echo "  Homebrew installed."
else
    echo "  Homebrew $(brew --version | head -1)"
fi
echo ""

# ──────────────────────────────────────────────
# Step 2: Check / Install Python
# ──────────────────────────────────────────────
echo "[2/6] Checking Python..."
PYTHON_CMD=""
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
fi

if [ -z "$PYTHON_CMD" ]; then
    echo "  Python is not installed. Installing via Homebrew..."
    brew install python
    PYTHON_CMD="python3"
    echo "  Python installed."
else
    PY_VER=$($PYTHON_CMD --version 2>&1 | grep -oP '\d+\.\d+')
    PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)

    if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]; }; then
        echo "  Python $PY_VER is too old (need 3.9+). Upgrading..."
        brew upgrade python
        echo "  Python upgraded."
    else
        echo "  Python $PY_VER — OK"
    fi
fi
echo ""

# ──────────────────────────────────────────────
# Step 3: Check / Install ffmpeg
# ──────────────────────────────────────────────
echo "[3/6] Checking ffmpeg..."
if ! command -v ffmpeg &>/dev/null; then
    echo "  ffmpeg is not installed. Installing..."
    brew install ffmpeg
    echo "  ffmpeg installed."
else
    FF_VER=$(ffmpeg -version 2>&1 | head -1)
    echo "  $FF_VER"
fi
echo ""

# ──────────────────────────────────────────────
# Step 4: Install Python Dependencies
# ──────────────────────────────────────────────
echo "[4/6] Installing Python dependencies..."
cd "$SCRIPT_DIR/core"
"$PYTHON_CMD" -m pip install --upgrade pip --quiet
"$PYTHON_CMD" -m pip install -r requirements.txt
cd "$SCRIPT_DIR"
echo "  Dependencies installed."
echo ""

# ──────────────────────────────────────────────
# Step 5: Check / Install yt-dlp
# ──────────────────────────────────────────────
echo "[5/6] Checking converter tool..."
if ! command -v yt-dlp &>/dev/null; then
    echo "  Not installed. Installing via Homebrew..."
    brew install yt-dlp 2>/dev/null || "$PYTHON_CMD" -m pip install yt-dlp
    echo "  Installation complete."
else
    echo "  Already installed. Updating to latest for YouTube..."
    brew upgrade yt-dlp 2>/dev/null || "$PYTHON_CMD" -m pip install -U yt-dlp 2>/dev/null
    YT_VER=$(yt-dlp --version 2>&1)
    echo "  yt-dlp $YT_VER — OK"
fi
echo ""

# ──────────────────────────────────────────────
# Step 6: Create app launcher
# ──────────────────────────────────────────────
echo "[6/6] Creating app launcher..."
cat > app.sh << 'LAUNCHER'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
python3 core/run.py "$@"
LAUNCHER
chmod +x app.sh

echo "  app.sh created — you can now run: ./app.sh"

# Minimal SoniQ.app bundle so SoniQ appears in Launchpad / Applications
APP_DIR="$HOME/Applications/SoniQ.app"
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources"
cat > "$APP_DIR/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>SoniQ</string>
  <key>CFBundleDisplayName</key><string>SoniQ</string>
  <key>CFBundleIdentifier</key><string>com.reza.soniq</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>CFBundleExecutable</key><string>soniq</string>
</dict>
</plist>
PLIST
cat > "$APP_DIR/Contents/MacOS/soniq" << LAUNCHER2
#!/bin/bash
cd "$SCRIPT_DIR"
exec "$SCRIPT_DIR/app.sh" "\$@"
LAUNCHER2
chmod +x "$APP_DIR/Contents/MacOS/soniq"
cp "$SCRIPT_DIR/core/assets/icon.icns" "$APP_DIR/Contents/Resources/icon.icns" 2>/dev/null || true
echo "  Applications entry created (SoniQ in Launchpad)."
echo ""

# ──────────────────────────────────────────────
# Done
# ──────────────────────────────────────────────
echo -e "${GREEN}${BOLD}============================================"
echo "    INSTALLATION COMPLETE"
echo -e "============================================${NC}"
echo ""
echo "  What to do next:"
echo ""
echo "  1. Run SoniQ:"
echo "       ./app.sh download \"Artist - Title\""
echo "       ./app.sh batch songs.json"
echo "       ./app.sh --help"
echo ""
echo "  2. Or use Python directly:"
echo "       python3 core/run.py download \"Artist - Title\""
echo ""
echo "  All files are in the 'core' folder."
echo "  Configuration: ~/.soniq/config.json"
echo ""
