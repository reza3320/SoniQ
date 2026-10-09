#!/bin/bash
# SoniQ — Linux Installer (Debian / Ubuntu / Mint / Pop!_OS)
# Run this script to install everything needed:
#   chmod +x install-debian.sh
#   ./install-debian.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BOLD='\033[1m'
GREEN='\033[0;32m'
NC='\033[0m'

echo ""
echo "============================================"
echo "   SoniQ — Installation (Debian / Ubuntu)"
echo "   v$(cat "$SCRIPT_DIR/VERSION" 2>/dev/null || echo "unknown")"
echo "============================================"
echo ""
if [ -f "$SCRIPT_DIR/app.sh" ]; then
    echo "   Existing installation found — updating in place."
    echo "   Your settings, logs and downloads are preserved."
    echo ""
fi

# ──────────────────────────────────────────────
# Step 1: Update package lists
# ──────────────────────────────────────────────
echo "[1/6] Updating package lists..."
sudo apt update -qq
echo "  Done."
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
    echo "  Python is not installed. Installing..."
    sudo apt install -y python3 python3-pip python3-venv
    PYTHON_CMD="python3"
    echo "  Python installed."
else
    PY_VER=$($PYTHON_CMD --version 2>&1 | grep -oP '\d+\.\d+')
    PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)

    if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]; }; then
        echo "  Python $PY_VER is too old (need 3.9+). Installing newer version..."
        sudo apt install -y python3 python3-pip python3-venv
        echo "  Python upgraded."
    else
        echo "  Python $PY_VER — OK"
    fi

    # Ensure pip is installed
    if ! command -v pip3 &>/dev/null && ! command -v pip &>/dev/null; then
        echo "  pip not found. Installing..."
        sudo apt install -y python3-pip
    fi
fi
echo ""

# ──────────────────────────────────────────────
# Step 3: Check / Install ffmpeg
# ──────────────────────────────────────────────
echo "[3/6] Checking ffmpeg..."
if ! command -v ffmpeg &>/dev/null; then
    echo "  ffmpeg is not installed. Installing..."
    sudo apt install -y ffmpeg
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

if command -v pip3 &>/dev/null; then
    PIP_CMD="pip3"
else
    PIP_CMD="pip"
fi

$PIP_CMD install --upgrade pip --quiet 2>/dev/null || true
$PIP_CMD install -r requirements.txt

cd "$SCRIPT_DIR"
echo "  Dependencies installed."
echo ""

# ──────────────────────────────────────────────
# Step 5: Check / Install yt-dlp
# ──────────────────────────────────────────────
echo "[5/6] Checking converter tool..."
if ! command -v yt-dlp &>/dev/null; then
    echo "  Not installed. Installing..."
    sudo apt install -y yt-dlp 2>/dev/null || $PIP_CMD install yt-dlp
    echo "  Installation complete."
else
    echo "  Already installed. Updating to latest for YouTube..."
    $PIP_CMD install -U yt-dlp 2>/dev/null
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

# Desktop menu entry so SoniQ appears in the applications menu
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_DIR/soniq.desktop" << DESKTOP
[Desktop Entry]
Type=Application
Name=SoniQ
Comment=High-quality music downloader
Exec=$SCRIPT_DIR/app.sh
Icon=$SCRIPT_DIR/core/assets/icon.png
Terminal=true
Categories=AudioVideo;Audio;Utility;
DESKTOP
echo "  Applications-menu entry created."

# Desktop shortcut (best effort - some desktops require trusting it once)
if [ -d "$HOME/Desktop" ]; then
    cp "$DESKTOP_DIR/soniq.desktop" "$HOME/Desktop/soniq.desktop" 2>/dev/null || true
    chmod +x "$HOME/Desktop/soniq.desktop" 2>/dev/null || true
    gio set "$HOME/Desktop/soniq.desktop" metadata::trusted true 2>/dev/null || true
    echo "  Desktop shortcut created."
fi
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
echo ""
echo "  2. Or use Python directly:"
echo "       python3 core/run.py download \"Artist - Title\""
echo ""
echo "  All files are in the 'core' folder."
echo "  Configuration: ~/.soniq/config.json"
echo ""
