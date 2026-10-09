#!/bin/bash
# SoniQ — Linux Installer (Fedora / Red Hat / CentOS)
# Run this script to install everything needed:
#   chmod +x install-redhat.sh
#   ./install-redhat.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BOLD='\033[1m'
GREEN='\033[0;32m'
NC='\033[0m'

echo ""
echo "============================================"
echo "   SoniQ — Installation (Fedora / Red Hat)"
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

# Check which package manager is available
if command -v dnf &>/dev/null; then
    PKG_MGR="dnf"
elif command -v yum &>/dev/null; then
    PKG_MGR="yum"
else
    echo "  ERROR: Neither dnf nor yum found. This script supports Fedora, RHEL, and CentOS only."
    exit 1
fi

sudo $PKG_MGR check-update -qq 2>/dev/null || true
echo "  Using $PKG_MGR"
echo ""

# ──────────────────────────────────────────────
# Step 2: Enable EPEL (for ffmpeg) if on RHEL/CentOS
# ──────────────────────────────────────────────
echo "[2/7] Checking for extra repositories..."

if [ "$PKG_MGR" = "yum" ]; then
    if ! rpm -q epel-release &>/dev/null; then
        echo "  EPEL not found. Installing EPEL (needed for ffmpeg)..."
        sudo yum install -y epel-release
        # Also enable RPM Fusion for ffmpeg
        sudo yum install -y --nogpgcheck https://mirrors.rpmfusion.org/free/el/rpmfusion-free-release-$(rpm -E %rhel).noarch.rpm
    fi
elif [ "$PKG_MGR" = "dnf" ]; then
    # Fedora has ffmpeg in the main repos, RHEL needs EPEL
    if grep -qi "rhel\|centos" /etc/os-release 2>/dev/null; then
        if ! rpm -q epel-release &>/dev/null; then
            echo "  Installing EPEL..."
            sudo dnf install -y epel-release
            sudo dnf install -y --nogpgcheck https://mirrors.rpmfusion.org/free/el/rpmfusion-free-release-$(rpm -E %rhel).noarch.rpm
        fi
    fi
fi
echo "  Done."
echo ""

# ──────────────────────────────────────────────
# Step 3: Check / Install Python
# ──────────────────────────────────────────────
echo "[3/7] Checking Python..."

PYTHON_CMD=""
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
fi

if [ -z "$PYTHON_CMD" ]; then
    echo "  Python is not installed. Installing..."
    sudo $PKG_MGR install -y python3 python3-pip
    PYTHON_CMD="python3"
    echo "  Python installed."
else
    PY_VER=$($PYTHON_CMD --version 2>&1 | grep -oP '\d+\.\d+')
    PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)

    if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]; }; then
        echo "  Python $PY_VER is too old (need 3.9+). Installing newer..."
        sudo $PKG_MGR install -y python3 python3-pip
        echo "  Python upgraded."
    else
        echo "  Python $PY_VER — OK"
    fi
fi
echo ""

# ──────────────────────────────────────────────
# Step 4: Check / Install ffmpeg
# ──────────────────────────────────────────────
echo "[4/7] Checking ffmpeg..."
if ! command -v ffmpeg &>/dev/null; then
    echo "  ffmpeg is not installed. Installing..."
    sudo $PKG_MGR install -y ffmpeg
    echo "  ffmpeg installed."
else
    FF_VER=$(ffmpeg -version 2>&1 | head -1)
    echo "  $FF_VER"
fi
echo ""

# ──────────────────────────────────────────────
# Step 5: Install Python Dependencies
# ──────────────────────────────────────────────
echo "[5/7] Installing Python dependencies..."

cd "$SCRIPT_DIR/core"

PIP_CMD="pip3"
if ! command -v pip3 &>/dev/null; then
    PIP_CMD="pip"
fi

$PIP_CMD install --upgrade pip --quiet 2>/dev/null || true
$PIP_CMD install -r requirements.txt

cd "$SCRIPT_DIR"
echo "  Dependencies installed."
echo ""

# ──────────────────────────────────────────────
# Step 6: Check / Install yt-dlp
# ──────────────────────────────────────────────
echo "[6/7] Checking converter tool..."
if ! command -v yt-dlp &>/dev/null; then
    echo "  Not installed. Installing..."
    $PIP_CMD install yt-dlp
    echo "  Installation complete."
else
    echo "  Already installed. Updating to latest for YouTube..."
    $PIP_CMD install -U yt-dlp 2>/dev/null
    YT_VER=$(yt-dlp --version 2>&1)
    echo "  yt-dlp $YT_VER — OK"
fi
echo ""

# ──────────────────────────────────────────────
# Step 7: Create app launcher
# ──────────────────────────────────────────────
echo "[7/7] Creating app launcher..."
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
