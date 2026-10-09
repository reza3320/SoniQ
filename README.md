# SoniQ
# SoniQ — High-Quality Music Downloader

```
                .-.
               (   )
                | |
                | |
    ,__________| |__________
   |  ________   ________  |
   | |        | |        | |
   | |  SoniQ | |  v0.2.32  | |
   | |________| |________| |
   |_______________________|
        _|___________|_
       /_______________\
       |||||||||||||||||
```

SoniQ downloads your music at the best possible quality, automatically
selecting the optimal source for every song. You tell it what you want,
it handles the rest.

## Features

- High-quality audio (targeting 320 kbps MP3)
- Automatic source selection (you never need to know where it comes from)
- Single song and batch modes (JSON or CSV input)
- Metadata cleanup (no leftover source identifiers in your files)
- Download diagnostics (know exactly what succeeded and what failed)

## Requirements

- **Python 3.9 or newer** ([python.org](https://python.org))
- **ffmpeg** (required by the converter tool — see platform install below)
- An internet connection

## Installation

### Choose your platform installer

| Platform | File to run |
|----------|------------|
| **Windows** | Double-click `install.bat` |
| **macOS** | Open Terminal, type: `chmod +x install-macos.sh && ./install-macos.sh` |
| **Linux (Ubuntu / Debian / Pop!_OS / Mint)** | Open terminal, type: `chmod +x install-debian.sh && ./install-debian.sh` |
| **Linux (Fedora / RHEL / CentOS)** | Open terminal, type: `chmod +x install-redhat.sh && ./install-redhat.sh` |

Each installer will handle everything automatically:
- Check if Python 3.9+ is installed → if missing, install it / if outdated, update it
- Check if ffmpeg is installed → if missing, install it
- Check the converter tool (yt-dlp) → if missing, install it
- Install all Python dependencies from requirements.txt
- Create an `app.bat` (Windows) or `app.sh` (macOS/Linux) launcher file
- Add SoniQ to your Start Menu and Desktop (Windows) or applications menu (macOS/Linux), with its icon
- Detect an existing installation and update it in place (settings, logs and downloads preserved)

Let the installer run. When you see "INSTALLATION COMPLETE", you are ready.

After installation you can use the app any time from your **Start Menu**
(Windows), your **applications menu** (Linux), or the **Desktop shortcut** —
or by double-clicking `app.bat` (Windows) / running `./app.sh`
(Linux/macOS) inside the SoniQ folder.

---

### Manual installation (if the installer does not work)

#### Step 1: Install Python

**Windows**
1. Open a web browser and go to https://www.python.org/downloads/
2. Click the yellow "Download Python" button (get version 3.9 or newer)
3. When the installer finishes downloading, double-click it
4. **IMPORTANT**: At the bottom of the first screen, check the box that says **"Add Python to PATH"**
5. Click "Install Now" and wait for it to finish
6. Close the installer
7. Open a command prompt (press Windows key, type `cmd`, press Enter)
8. Type this command and press Enter to verify:
   ```
   python --version
   ```
   You should see something like: `Python 3.13.2`

**macOS**
1. Open Terminal (press Cmd+Space, type `Terminal`, press Enter)
2. If you have [Homebrew](https://brew.sh/) installed, type:
   ```
   brew install python
   ```
   Wait for it to finish.
3. If you do not have Homebrew, go to https://www.python.org/downloads/ instead
4. Click the yellow "Download Python" button
5. Open the downloaded file and follow the installer steps
6. Open Terminal and type:
   ```
   python3 --version
   ```
   You should see something like: `Python 3.13.2`

**Linux (Ubuntu / Debian)**
1. Open a terminal (Ctrl+Alt+T)
2. Type this command and press Enter:
   ```
   sudo apt update
   ```
3. Type this command and press Enter:
   ```
   sudo apt install python3 python3-pip python3-venv -y
   ```
4. Type this to verify:
   ```
   python3 --version
   ```
   You should see something like: `Python 3.13.2`

**Linux (Fedora)**
1. Open a terminal
2. Type:
   ```
   sudo dnf install python3 python3-pip -y
   ```
3. Verify:
   ```
   python3 --version
   ```

**Linux (Arch)**
1. Open a terminal
2. Type:
   ```
   sudo pacman -S python python-pip --noconfirm
   ```
3. Verify:
   ```
   python3 --version
   ```

---

### Step 2: Install ffmpeg

The converter tool (installed in Step 5) needs ffmpeg to process audio.

**Windows**
1. Press Windows key, type `cmd`, press Enter
2. Type this command and press Enter:
   ```
   winget install ffmpeg
   ```
   If winget does not work, go to https://ffmpeg.org/download.html and follow
   the Windows installation guide.
3. Verify:
   ```
   ffmpeg -version
   ```

**macOS**
1. Open Terminal
2. If you have Homebrew, type:
   ```
   brew install ffmpeg
   ```
3. Verify:
   ```
   ffmpeg -version
   ```

**Linux (Ubuntu / Debian)**
1. Open terminal and type:
   ```
   sudo apt install ffmpeg -y
   ```
2. Verify:
   ```
   ffmpeg -version
   ```

**Linux (Fedora)**
1. Open terminal and type:
   ```
   sudo dnf install ffmpeg -y
   ```
2. Verify:
   ```
   ffmpeg -version
   ```

**Linux (Arch)**
1. Open terminal and type:
   ```
   sudo pacman -S ffmpeg --noconfirm
   ```
2. Verify:
   ```
   ffmpeg -version
   ```

---

### Step 3: Get the application

You need to download the SoniQ files to your computer.

**Option A: Download the ZIP file**
1. Open a web browser and go to https://github.com/reza3320/SoniQ
2. Click the green "Code" button
3. Click "Download ZIP"
4. Extract the ZIP file to a folder on your computer
5. Open a terminal (or command prompt on Windows) and go to that folder:
   ```
   cd path/to/soniq-folder
   ```

**Option B: Clone with git**
1. Open a terminal (or command prompt on Windows)
2. Type:
   ```
   git clone https://github.com/reza3320/SoniQ.git
   ```
3. Go into the folder:
   ```
   cd soniq
   ```

After this step, you should be inside the `soniq` folder. If you type `dir` (Windows)
or `ls` (macOS/Linux), you should see files like `run.py`, `README.md`, etc.

---

### Step 4: Install Python dependencies

**Windows**
1. Open a command prompt in the soniq folder
2. (Optional but recommended) Create a virtual environment:
   ```
   python -m venv venv
   ```
3. Activate the virtual environment:
   ```
   venv\Scripts\activate
   ```
   You should see `(venv)` appear at the start of the command line.
4. Install the required packages:
   ```
   pip install -r requirements.txt
   ```
   Wait for it to finish. You will see a progress bar and then a success message.
5. If you skipped the virtual environment, just run:
   ```
   pip install -r requirements.txt
   ```

**macOS / Linux**
1. Open a terminal in the soniq folder
2. (Optional but recommended) Create a virtual environment:
   ```
   python3 -m venv venv
   ```
3. Activate the virtual environment:
   ```
   source venv/bin/activate
   ```
   You should see `(venv)` appear at the start of the command line.
4. Install the required packages:
   ```
   pip install -r requirements.txt
   ```
   Wait for it to finish.
5. If you skipped the virtual environment, just run:
   ```
   pip3 install -r requirements.txt
   ```

---

### Step 5: Install the converter tool

**Windows**
1. Open a command prompt
2. Type one of these:
   ```
   winget install yt-dlp
   ```
   OR (if winget does not work):
   ```
   pip install yt-dlp
   ```
3. Verify it installed correctly:
   ```
   yt-dlp --version
   ```

**macOS**
1. Open Terminal
2. Type one of these:
   ```
   brew install yt-dlp
   ```
   OR:
   ```
   pip3 install yt-dlp
   ```
3. Verify:
   ```
   yt-dlp --version
   ```

**Linux (Ubuntu / Debian)**
1. Open terminal
2. Try:
   ```
   sudo apt install yt-dlp -y
   ```
   If that does not work, use pip:
   ```
   pip3 install yt-dlp
   ```
3. Verify:
   ```
   yt-dlp --version
   ```

**Linux (Fedora / Arch)**
1. Open terminal
2. Use pip:
   ```
   pip3 install yt-dlp
   ```
3. Verify:
   ```
   yt-dlp --version
   ```

---

You are now ready to use SoniQ. Proceed to Quick Start below.

## Quick Start

```bash
# Make sure you are in the SoniQ folder (the one with app.bat or app.sh)

# Windows
app.bat download "Artist Name - Song Title"

# macOS / Linux
./app.sh download "Artist Name - Song Title"

# Single song (alternative format)
./app.sh download "Artist" "Title"

# Batch download from a JSON file
./app.sh batch songs.json

# Batch download from a CSV file
./app.sh batch songs.csv

# Show help
./app.sh --help

# Show version
./app.sh --version
```

## Batch File Format

JSON:
```json
{
  "songs": [
    {"artist": "Radiohead", "title": "Creep"},
    {"artist": "Bruno Mars", "title": "Locked Out of Heaven"}
  ]
}
```

CSV:
```csv
artist,title
Radiohead,Creep
Bruno Mars,Locked Out of Heaven
```

## Output

Files are saved to `~/Music/SoniQ/` by default (configurable in
`~/.soniq/config.json`). Each file is named as `Title - Artist.mp3`
with clean metadata and no identifying marks from the source.

### Windows users

`~/Music/SoniQ/` translates to `C:\Users\YourName\Music\SoniQ\`

### Changing the output directory

Edit `~/.soniq/config.json` (or `C:\Users\YourName\.soniq\config.json` on Windows):

```json
{
  "output_dir": "D:/MyMusic"
}
```

In the interactive app you can also type `/output` to see the current
folder, or `/output D:/MyMusic` to change it. The first time you open
the app it asks where to save, and remembers your answer.

## Diagnostics

After each run, a JSON report is saved to `~/.soniq/diagnostics/`, and
a plain-text log is kept in `~/.soniq/logs/soniq.log` (outside the
app folder) — open it to see what happened and why, run by run.
View the latest report:

```bash
./app.sh --diagnostics
```

## Updating SoniQ

1. Download the newest release zip
2. Extract it **into your SoniQ folder**, choosing "Replace" when asked
   (settings and logs in `~/.soniq/`, and your downloaded
   songs are all preserved)
3. Run the installer once more (`install.bat` / `install-debian.sh` /
   `install-redhat.sh` / `install-macos.sh`) — it updates in place

The installer prints "Existing installation found — updating in place"
when it detects an older copy.

SoniQ also quietly checks for newer versions when it starts (max a few
seconds; completely silent when offline). Release files are named
`soniq-vX.Y.Z-github.zip`.

## Uninstalling SoniQ

Run `uninstall.bat` (Windows) or `./uninstall.sh` (macOS/Linux) from the
SoniQ folder. It removes the Start Menu / applications-menu entry, the
launcher and caches, and (optionally) your settings and logs. Your
downloaded songs are never touched. To finish, delete the SoniQ folder.

## Tray + mini terminal (Windows)

Run `tray.bat` (or just open SoniQ — the tray icon comes up with it) —
SoniQ appears as a small icon near the clock, and one background
session starts with it.

- **Click the icon once** → the mini SoniQ window opens (fixed at the
  bottom edge, set size — clicking the icon again, pressing Esc, or
  clicking anywhere outside hides it): type commands
  at the bottom (`/download Artist - Title`, `/url <link>`,
  `/playlist <url>`, `/batch <file>`, `/retry` to re-run the last
  failures, `/cancel`), see results, scroll back through history, and
  watch the live progress bar while a download runs (a Cancel button
  appears with it). Up/Down recall commands — the history is shared
  with the CLI app and kept between sessions; clicking anywhere in the
  window puts the caret back in the input line; Esc (or clicking the
  icon again) hides the window — the session keeps running and
  downloads continue in the background.
- **Double-click the icon** → opens the classic SoniQ CLI console (the
  full terminal app). Only one SoniQ Tray ever runs — starting it
  again just reuses it, and only one CLI console can be open at a
  time (a second one closes itself and brings the first to the front).
- **Right-click the icon** → Open SoniQ · Open downloads folder ·
  Open log folder · Settings… · Start with Windows · Quit.
- Downloads that finish while the window is hidden pop a notification
  — click it to open the song's folder.
- Settings has notification toggles and an optional clipboard watch
  (copy a YouTube link and SoniQ offers to download it).

Choose "Start with Windows" and SoniQ Tray loads silently when you log
in — no window, just the icon.

Opening the app (`app.bat`) also brings the tray icon up automatically,
so the whole app is always reachable from there.

The CLI shares the same command history — ↑ works in it too, and
`/history` lists the last 15 commands. Both surfaces also remember the
recent conversation: reopen the CLI or the tray window and the last
messages (like the `/help` output) are shown again, marked
"previous messages" — and while the tray window is open, new messages
from the CLI appear in it live; the same works in the other direction,
no reopening needed.

## Troubleshooting

| Problem | Likely fix |
|---------|-----------|
| `No module named soniq` | You are not in the right directory. `cd` into the SoniQ folder first (the one with app.sh). |
| `app.sh: command not found` | You need to run `chmod +x app.sh` first, or use `bash app.sh` instead. |
| `yt-dlp not found` | Install yt-dlp (the installer script handles this). Run `install-debian.sh` or `install-redhat.sh`. |
| `ffmpeg not found` | Install ffmpeg (the installer script handles this). Run the appropriate installer for your OS. |
| `Permission denied` | On Linux/macOS, run `chmod +x app.sh` to make the launcher executable. |
| Download always fails | The primary source may be unreachable in your region. The app will fall back automatically. |

## License

MIT License — see LICENSE file for details.
Copyright (c) 2026 Reza Azimi. All rights reserved.

## Legal Disclaimer

**We take no responsibility for any misuse of this app.** This is just
a tool from us for experimenting — if you intend to download copyrighted
files, YouTube files, or music, the user is accountable for everything.

SoniQ is a **tool for locating and organizing publicly available audio content**.
It does not host, store, stream, or distribute any copyrighted material.

1. **No hosting.** SoniQ does not maintain any database of music files,
   nor does it operate any servers that store audio content. It is a
   search-and-download automation tool, functionally equivalent to a web
   browser or a feed reader.

2. **No ownership transfer.** The audio files you obtain using this tool
   are already publicly accessible through the sources this tool queries.
   SoniQ does not circumvent any paywall, authentication system, or
   access control mechanism. It only retrieves content that is already
   freely available at the source URL.

3. **User responsibility.** You, the user, are the one who initiates the
   search and the download. SoniQ executes these actions on your behalf
   under your direction, the same way a web browser downloads a file when
   you click a link. You are solely responsible for ensuring that your
   use of downloaded content complies with applicable copyright laws in
   your jurisdiction.

4. **Fair use / Educational purpose.** This tool is designed for personal,
   educational, and research use cases such as:
   - Building personal backup archives of music you already own
   - Academic study of audio encoding and bitrate perception
   - Testing and comparing audio quality across different formats
   - Creating timecoded or trimmed excerpts for criticism or commentary

5. **No endorsement.** SoniQ is not affiliated with, endorsed by, or
   connected to any of the sources it queries. All product names, logos,
   and brands are property of their respective owners.

6. **Compliance.** If you believe SoniQ facilitates access to your
   copyrighted material in a way that violates your rights, please
   contact the repository owner. We take all legitimate takedown
   requests seriously and will act promptly.

**In short: SoniQ finds what is already there. It does not create,
store, or redistribute anything. The user decides what to download
and bears full responsibility for that decision.**

