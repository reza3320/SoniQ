# SoniQ tray host (Windows) - mini terminal + quick downloads.
# Started by tray.bat; runs hidden with no console window.
#
# Left-click the tray icon  -> opens the mini SoniQ terminal window:
#   type commands at the bottom (/download Artist - Title, /url <link>,
#   /playlist <url>, /batch <file>, /cancel); results, history and live
#   download progress appear in the window. Closing the window hides it;
#   downloads keep running in the background session.
# Right-click the icon -> menu (open window, downloads folder, log
#   folder, start with Windows, quit).

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$Root = $PSScriptRoot
if (-not $Root) { $Root = Split-Path -Parent $MyInvocation.MyCommand.Path }

$PythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCmd) {
    [System.Windows.Forms.MessageBox]::Show("Python was not found. Run install.bat first.")
    exit 1
}
$Python = $PythonCmd.Source

# Single instance: only one SoniQ Tray at a time.
$script:mutexCreated = $false
$script:instanceMutex = New-Object System.Threading.Mutex($true, "Local\SoniQ_Tray", [ref]$script:mutexCreated)
if (-not $script:mutexCreated) {
    # Already running - exit quietly (a second tray is never wanted).
    exit 0
}

$trayIcon = New-Object System.Drawing.Icon((Join-Path $Root "core\assets\tray.ico"))
$tray = New-Object System.Windows.Forms.NotifyIcon
$tray.Icon = $trayIcon
$tray.Text = "SoniQ"
$tray.Visible = $true

$script:closeToTray = $true   # overridden from config below

# ---------------------------------------------------------------------------
# Background worker (one persistent "run.py session" process)
# ---------------------------------------------------------------------------

$script:worker = $null
$script:workerIn = $null
$script:outTask = $null
$script:errTask = $null

function Get-Worker {
    if ($script:worker -and -not $script:worker.HasExited) { return }
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Python
    $psi.Arguments = '-B "' + (Join-Path $Root "core\run.py") + '" session'
    $psi.WorkingDirectory = $Root
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    $null = $proc.Start()
    $script:worker = $proc
    $script:workerIn = New-Object System.IO.StreamWriter($proc.StandardInput.BaseStream, (New-Object System.Text.UTF8Encoding($false)))
    $script:workerIn.AutoFlush = $true
    $script:outTask = $proc.StandardOutput.ReadLineAsync()
    $script:errTask = $proc.StandardError.ReadLineAsync()
    $script:timer.Start()
}

function Stop-Worker {
    if (-not $script:worker) { return }
    try {
        $script:workerIn.WriteLine("/cancel")
        $script:workerIn.WriteLine("/quit")
        $script:workerIn.Flush()
    } catch { }
    try { if (-not $script:worker.WaitForExit(2500)) { $script:worker.Kill() } } catch { }
    $script:worker = $null
    $script:workerIn = $null
    $script:outTask = $null
    $script:errTask = $null
}

# ---------------------------------------------------------------------------
# Mini terminal window
# ---------------------------------------------------------------------------

$form = New-Object System.Windows.Forms.Form
$form.Text = "SoniQ"
$form.FormBorderStyle = 'None'
$form.ClientSize = New-Object System.Drawing.Size(700, 430)
$form.MinimumSize = New-Object System.Drawing.Size(420, 260)
$form.MaximizeBox = $false
$form.ShowInTaskbar = $false
$form.Icon = $trayIcon
$form.BackColor = [System.Drawing.ColorTranslator]::FromHtml("#1E1E1E")
$form.KeyPreview = $true
$form.StartPosition = 'Manual'
$workArea = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
$form.Location = New-Object System.Drawing.Point(($workArea.Right - $form.Width - 16), ($workArea.Bottom - $form.Height - 16))

$rtb = New-Object System.Windows.Forms.RichTextBox
$rtb.Dock = 'Fill'
$rtb.ReadOnly = $true
$rtb.TabStop = $false
$rtb.BackColor = [System.Drawing.ColorTranslator]::FromHtml("#1E1E1E")
$rtb.ForeColor = [System.Drawing.ColorTranslator]::FromHtml("#D4D4D4")
$rtb.Font = New-Object System.Drawing.Font("Consolas", 9.5)
$rtb.BorderStyle = 'None'
$rtb.WordWrap = $true
$rtb.HideSelection = $false
$form.Controls.Add($rtb)

$script:progressRow = New-Object System.Windows.Forms.Panel
$script:progressRow.Dock = 'Bottom'
$script:progressRow.Height = 26
$script:progressRow.Visible = $false
$script:progressRow.BackColor = [System.Drawing.ColorTranslator]::FromHtml("#1E1E1E")
$script:barLabel = New-Object System.Windows.Forms.Label
$script:barLabel.Dock = 'Left'
$script:barLabel.Width = 170
$script:barLabel.ForeColor = [System.Drawing.ColorTranslator]::FromHtml("#C9A7FF")
$script:barLabel.TextAlign = 'MiddleLeft'
$script:bar = New-Object System.Windows.Forms.ProgressBar
$script:bar.Dock = 'Fill'
$script:bar.Minimum = 0
$script:bar.Maximum = 100
$script:btnCancelDl = New-Object System.Windows.Forms.Button
$script:btnCancelDl.Text = "Cancel"
$script:btnCancelDl.Dock = 'Right'
$script:btnCancelDl.Width = 70
$script:btnCancelDl.Add_Click({ Send-Command "/cancel"; $inputBox.Focus() })
$script:progressRow.Controls.Add($script:bar)
$script:progressRow.Controls.Add($script:btnCancelDl)
$script:progressRow.Controls.Add($script:barLabel)
$form.Controls.Add($script:progressRow)

$inputRow = New-Object System.Windows.Forms.Panel
$inputRow.Dock = 'Bottom'
$inputRow.Height = 30
$inputRow.BackColor = [System.Drawing.ColorTranslator]::FromHtml("#2D2D2D")
$inputBox = New-Object System.Windows.Forms.TextBox
$inputBox.Dock = 'Fill'
$inputBox.BorderStyle = 'None'
$inputBox.BackColor = [System.Drawing.ColorTranslator]::FromHtml("#2D2D2D")
$inputBox.ForeColor = [System.Drawing.ColorTranslator]::FromHtml("#E8E8E8")
$inputBox.Font = New-Object System.Drawing.Font("Consolas", 10)
$inputRow.Controls.Add($inputBox)
$form.Controls.Add($inputRow)

# Clicking anywhere keeps the keyboard focus on the input line - the
# output pane must never keep focus (caret always ready for typing).
$rtb.Add_Enter({ $inputBox.Focus() })
$rtb.Add_MouseDown({ $inputBox.Focus() })
$form.Add_MouseClick({ $inputBox.Focus() })
$script:progressRow.Add_MouseClick({ $inputBox.Focus() })
$inputRow.Add_MouseClick({ $inputBox.Focus() })

function Add-Line([string]$Text, [string]$Color) {
    $rtb.SelectionStart = $rtb.TextLength
    $rtb.SelectionLength = 0
    $rtb.SelectionColor = [System.Drawing.ColorTranslator]::FromHtml($Color)
    $rtb.AppendText($Text + "`r`n")
    $rtb.SelectionColor = $rtb.ForeColor
    $rtb.ScrollToCaret()
    Transcript-Append $Text
}

function Set-Busy([bool]$Busy) {
    if ($Busy) {
        $script:progressRow.Visible = $true
    } else {
        $script:progressRow.Visible = $false
        $script:bar.Value = 0
        $script:barLabel.Text = ""
    }
}

$script:notifications = $true
$script:lastBalloonFolder = ""
$script:pendingClipUrl = $null

function Notify([string]$Title, [string]$Message, [string]$Kind) {
    if (-not $script:notifications) { return }
    $icon = [System.Windows.Forms.ToolTipIcon]::Info
    if ($Kind -eq "Error") { $icon = [System.Windows.Forms.ToolTipIcon]::Error }
    $tray.ShowBalloonTip(5000, $Title, $Message, $icon)
}

$script:hist = New-Object System.Collections.ArrayList
$script:histIdx = 0
$script:histFile = Join-Path $env:USERPROFILE ".soniq\history.txt"
$script:histLegacy = Join-Path $env:USERPROFILE ".soniq\tray_history.txt"

function Load-History {
    # Shared with the CLI (cli.py writes the same file): reloading picks
    # up commands typed in the CLI console since this window last opened.
    $script:hist.Clear()
    try {
        if (-not (Test-Path $script:histFile) -and (Test-Path $script:histLegacy)) {
            Copy-Item $script:histLegacy $script:histFile -Force -ErrorAction SilentlyContinue
        }
        if (Test-Path $script:histFile) {
            foreach ($h in (Get-Content $script:histFile -Tail 200)) {
                if ($h.Trim()) { $null = $script:hist.Add($h.Trim()) }
            }
        }
    } catch { }
    $script:histIdx = $script:hist.Count
}
Load-History

$script:transcriptFile = Join-Path $env:USERPROFILE ".soniq\transcript.log"
$script:transcriptReplaying = $false
$script:transcriptSeen = 0
$script:transcriptPollTick = 0
$script:suppressDeactivate = $false
$script:lastAutoHide = [datetime]::MinValue

function Transcript-Append([string]$Text) {
    # Shared "chat" log with the CLI (transcript.py writes the same file).
    if ($script:transcriptReplaying) { return }
    if (-not $Text -or -not $Text.Trim()) { return }
    try {
        $tDir = Split-Path $script:transcriptFile
        if (-not (Test-Path $tDir)) { $null = New-Item -ItemType Directory -Path $tDir -Force }
        Add-Content -Path $script:transcriptFile -Value $Text -Encoding UTF8
        $script:transcriptSeen++
        $tFile = Get-Item $script:transcriptFile -ErrorAction SilentlyContinue
        if ($tFile -and $tFile.Length -gt 400000) {
            $tAll = @(Get-Content $script:transcriptFile)
            $tAll | Select-Object -Last 2000 | Set-Content -Path $script:transcriptFile -Encoding UTF8
        }
    } catch { }
}

function Update-TranscriptView {
    # Shows lines added since this window last looked (typed in the CLI,
    # or by the tray itself while this window was hidden).
    try {
        if (-not (Test-Path $script:transcriptFile)) { return }
        $all = @(Get-Content $script:transcriptFile)
        $total = $all.Count
        if ($total -lt $script:transcriptSeen) { $script:transcriptSeen = 0 }
        $delta = $total - $script:transcriptSeen
        if ($delta -le 0) { return }
        $show = [Math]::Min($delta, 60)
        $start = $total - $show
        $newLines = @($all[$start..($total - 1)])
        $script:transcriptReplaying = $true
        if ($script:transcriptSeen -eq 0) {
            Add-Line "--- previous messages ---" "#8A8A8A"
        } else {
            Add-Line "--- new messages ---" "#8A8A8A"
        }
        foreach ($p in $newLines) { Add-Line $p "#9A9A9A" }
        $script:transcriptReplaying = $false
        $script:transcriptSeen = $total
    } catch { $script:transcriptReplaying = $false }
}

function Send-Command([string]$Text) {
    $Text = $Text.Trim()
    if (-not $Text) { return }
    Get-Worker
    $null = $script:hist.Add($Text)
    $script:histIdx = $script:hist.Count
    try {
        $histDir = Split-Path $script:histFile
        if (-not (Test-Path $histDir)) { $null = New-Item -ItemType Directory -Path $histDir -Force }
        $last = ""
        if (Test-Path $script:histFile) { $last = Get-Content $script:histFile -Tail 1 }
        if ($last -ne $Text) {
            Add-Content -Path $script:histFile -Value $Text -Encoding UTF8
        }
        $all = @(Get-Content $script:histFile -ErrorAction SilentlyContinue)
        if ($all.Count -gt 700) {
            $all | Select-Object -Last 500 | Set-Content -Path $script:histFile -Encoding UTF8
        }
    } catch { }
    Add-Line ("soniq> " + $Text) "#7FD1FF"
    try {
        $script:workerIn.WriteLine($Text)
        $script:workerIn.Flush()
    } catch {
        Add-Line "(the session is not reachable - it will restart on the next command)" "#FF7B72"
        $script:worker = $null
    }
}

function Handle-WorkerLine([string]$Line) {
    $obj = $null
    try { $obj = $Line | ConvertFrom-Json } catch { Add-Line $Line "#D4D4D4"; return }
    if (-not $obj.type) { Add-Line $Line "#D4D4D4"; return }
    switch ($obj.type) {
        "ready" {
            Add-Line ("session ready (SoniQ v" + $obj.version + ")") "#8A8A8A"
        }
        "log" {
            Add-Line $obj.text "#D4D4D4"
        }
        "progress" {
            $pct = [int][math]::Round([double]$obj.pct)
            if ($pct -lt 0) { $pct = 0 }
            if ($pct -gt 100) { $pct = 100 }
            $script:bar.Value = $pct
            $script:barLabel.Text = "Downloading... " + $pct + "%"
            Set-Busy $true
        }
        "result" {
            $song = $obj.song
            if ($song.status -eq "success") {
                Add-Line ("  OK [" + $song.quality + "] " + $song.artist + " - " + $song.title) "#7CE38B"
                Add-Line ("  File: " + $song.file) "#7CE38B"
                $script:lastBalloonFolder = Split-Path $song.file
                if (-not $form.Visible) {
                    Notify "SoniQ" ("Done: " + $song.title + " - click to open the folder") "Info"
                }
            } else {
                $err = $song.error
                if (-not $err) { $err = $song.error_code }
                Add-Line ("  FAILED: " + $song.artist + " - " + $song.title + "  [" + $song.error_code + "] " + $err) "#FF7B72"
                $script:lastBalloonFolder = ""
                if (-not $form.Visible) {
                    Notify "SoniQ" ("Failed: " + $song.title) "Error"
                }
            }
        }
        "done" {
            Set-Busy $false
            if ($obj.cancelled) { Add-Line "(cancelled)" "#C9A7FF" }
        }
        "error" {
            Add-Line ("! " + $obj.message) "#FF7B72"
        }
        "cancelled" {
            Add-Line "(cancel requested)" "#C9A7FF"
        }
        "bye" {
            Add-Line "(session closed)" "#8A8A8A"
        }
        default {
            Add-Line $Line "#D4D4D4"
        }
    }
}

$script:timer = New-Object System.Windows.Forms.Timer
$script:timer.Interval = 100
$script:timer.Add_Tick({
    try {
        if ($script:outTask -and $script:outTask.IsCompleted) {
            $line = $script:outTask.Result
            if ($null -eq $line) {
                Add-Line "(session ended - it will restart on the next command)" "#C9A7FF"
                $script:worker = $null
                $script:workerIn = $null
                $script:outTask = $null
                $script:errTask = $null
                Set-Busy $false
            } else {
                if ($line.Trim()) { Handle-WorkerLine $line }
                if ($script:worker) { $script:outTask = $script:worker.StandardOutput.ReadLineAsync() }
            }
        }
        if ($script:errTask -and $script:errTask.IsCompleted) {
            $eline = $script:errTask.Result
            if ($null -ne $eline -and $eline.Trim()) { Add-Line $eline "#9A9A9A" }
            if ($script:worker) { $script:errTask = $script:worker.StandardError.ReadLineAsync() }
        }
    } catch { }
})

$script:fullMode = $false
$script:hintShown = $false

function Show-SoniqWindow([bool]$Full) {
    Get-Worker
    Load-History
    Update-TranscriptView
    if ($form.Visible -and ($Full -ne $script:fullMode)) { $form.Hide() }
    $script:fullMode = $Full
    $workArea = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    if ($Full) {
        $form.ShowInTaskbar = $true
        $form.ClientSize = New-Object System.Drawing.Size(1000, 650)
        $form.Location = New-Object System.Drawing.Point(([int](($workArea.Width - $form.Width) / 2) + $workArea.Left), ([int](($workArea.Height - $form.Height) / 2) + $workArea.Top))
    } else {
        $form.ShowInTaskbar = $false
        $form.ClientSize = New-Object System.Drawing.Size(700, 430)
        $form.Location = New-Object System.Drawing.Point(($workArea.Right - $form.Width - 16), ($workArea.Bottom - $form.Height - 16))
    }
    if (-not $form.Visible) { $form.Show() }
    $form.Activate()
    $form.BringToFront()
    $inputBox.Focus()
    if (-not $script:hintShown) {
        $script:hintShown = $true
        Add-Line "(tip: Esc or clicking the tray icon again hides this window - downloads keep running)" "#8A8A8A"
    }
}

function Show-SoniqMini {
    if ($form.Visible -and $script:fullMode) {
        $form.Activate()
        $inputBox.Focus()
        return
    }
    Show-SoniqWindow $false
}

$form.Add_FormClosing({
    param($sender, $e)
    if ($e.CloseReason -eq [System.Windows.Forms.CloseReason]::UserClosing) {
        if ($script:closeToTray) {
            $e.Cancel = $true
            $form.Hide()
        }
    }
})
$form.Add_Deactivate({
    # Clicking anywhere outside hides the window (feels like a popup).
    if (-not $script:suppressDeactivate -and $form.Visible) {
        $form.Hide()
        $script:lastAutoHide = Get-Date
    }
})
$form.Add_FormClosed({
    Stop-Worker
    $script:context.ExitThread()
})
$form.Add_KeyDown({
    param($sender, $e)
    if ($e.KeyCode -eq [System.Windows.Forms.Keys]::Escape) { $form.Hide() }
})

$inputBox.Add_KeyDown({
    param($sender, $e)
    if ($e.KeyCode -eq [System.Windows.Forms.Keys]::Enter) {
        $e.SuppressKeyPress = $true
        $text = $inputBox.Text
        $inputBox.Text = ""
        Send-Command $text
    } elseif ($e.KeyCode -eq [System.Windows.Forms.Keys]::Up) {
        $e.SuppressKeyPress = $true
        if ($script:hist.Count -gt 0 -and $script:histIdx -gt 0) {
            $script:histIdx--
            $inputBox.Text = $script:hist[$script:histIdx]
            $inputBox.SelectionStart = $inputBox.Text.Length
        }
    } elseif ($e.KeyCode -eq [System.Windows.Forms.Keys]::Down) {
        $e.SuppressKeyPress = $true
        if ($script:histIdx -lt ($script:hist.Count - 1)) {
            $script:histIdx++
            $inputBox.Text = $script:hist[$script:histIdx]
        } else {
            $script:histIdx = $script:hist.Count
            $inputBox.Text = ""
        }
    }
})

# ---------------------------------------------------------------------------
# Autostart + folders
# ---------------------------------------------------------------------------

function Get-StartupLinkPath {
    return (Join-Path ([Environment]::GetFolderPath('Startup')) "SoniQ Tray.lnk")
}

function Set-Autostart([bool]$Enabled) {
    $linkPath = Get-StartupLinkPath
    if ($Enabled) {
        $ws = New-Object -ComObject WScript.Shell
        $shortcut = $ws.CreateShortcut($linkPath)
        $shortcut.TargetPath = "wscript.exe"
        $shortcut.Arguments = '//nologo "' + (Join-Path $Root "tray.vbs") + '"'
        $shortcut.WorkingDirectory = $Root
        $shortcut.IconLocation = Join-Path $Root "core\assets\tray.ico"
        $shortcut.Description = "SoniQ Tray - quick downloads"
        $shortcut.WindowStyle = 7
        $shortcut.Save()
    } else {
        Remove-Item $linkPath -ErrorAction SilentlyContinue
    }
}

function Get-DownloadDir {
    $dir = $null
    try {
        $cfgPath = Join-Path $env:USERPROFILE ".soniq\config.json"
        if (Test-Path $cfgPath) {
            $cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json
            if ($cfg.output_dir) { $dir = $cfg.output_dir }
        }
    } catch { }
    if (-not $dir) { $dir = Join-Path $env:USERPROFILE "Music\SoniQ" }
    if (-not (Test-Path $dir)) { $null = New-Item -ItemType Directory -Path $dir -Force }
    return $dir
}

function Read-SoniqConfig {
    $cfgPath = Join-Path $env:USERPROFILE ".soniq\config.json"
    $result = $null
    try {
        if (Test-Path $cfgPath) { $result = Get-Content $cfgPath -Raw | ConvertFrom-Json }
    } catch { }
    return $result
}

function Get-ConfigValue([string]$Key, $Default) {
    $cfg = Read-SoniqConfig
    if ($cfg -and ($cfg.PSObject.Properties.Name -contains $Key)) { return $cfg.$Key }
    return $Default
}

function Save-SoniqConfig([hashtable]$Updates) {
    $cfgPath = Join-Path $env:USERPROFILE ".soniq\config.json"
    $cfg = @{}
    $existing = Read-SoniqConfig
    if ($existing) { $existing.PSObject.Properties | ForEach-Object { $cfg[$_.Name] = $_.Value } }
    foreach ($key in $Updates.Keys) { $cfg[$key] = $Updates[$key] }
    $dir = Split-Path $cfgPath
    if (-not (Test-Path $dir)) { $null = New-Item -ItemType Directory -Path $dir -Force }
    $json = $cfg | ConvertTo-Json -Depth 6
    [System.IO.File]::WriteAllText($cfgPath, $json, (New-Object System.Text.UTF8Encoding($false)))
}

function Show-SoniqSettings {
    $sf = New-Object System.Windows.Forms.Form
    $sf.Text = "SoniQ Settings"
    $sf.ClientSize = New-Object System.Drawing.Size(460, 326)
    $sf.FormBorderStyle = 'FixedDialog'
    $sf.MaximizeBox = $false
    $sf.MinimizeBox = $false
    $sf.StartPosition = 'CenterScreen'
    $sf.Icon = $trayIcon

    $cbAutostart = New-Object System.Windows.Forms.CheckBox
    $cbAutostart.Text = "Start SoniQ Tray when Windows starts"
    $cbAutostart.Location = New-Object System.Drawing.Point(16, 16)
    $cbAutostart.Width = 420
    $cbAutostart.Checked = Test-Path (Get-StartupLinkPath)
    $sf.Controls.Add($cbAutostart)

    $cbClose = New-Object System.Windows.Forms.CheckBox
    $cbClose.Text = "Closing the window hides it to the tray (uncheck: close quits SoniQ)"
    $cbClose.Location = New-Object System.Drawing.Point(16, 44)
    $cbClose.Width = 430
    $cbClose.Checked = [bool](Get-ConfigValue "close_to_tray" $true)
    $sf.Controls.Add($cbClose)

    $cbUpdates = New-Object System.Windows.Forms.CheckBox
    $cbUpdates.Text = "Check for new versions when the app starts"
    $cbUpdates.Location = New-Object System.Drawing.Point(16, 72)
    $cbUpdates.Width = 420
    $cbUpdates.Checked = [bool](Get-ConfigValue "check_for_updates" $true)
    $sf.Controls.Add($cbUpdates)

    $cbNotify = New-Object System.Windows.Forms.CheckBox
    $cbNotify.Text = "Show popup notifications when downloads finish"
    $cbNotify.Location = New-Object System.Drawing.Point(16, 100)
    $cbNotify.Width = 420
    $cbNotify.Checked = [bool](Get-ConfigValue "notifications" $true)
    $sf.Controls.Add($cbNotify)

    $cbClip = New-Object System.Windows.Forms.CheckBox
    $cbClip.Text = "Watch the clipboard for YouTube links"
    $cbClip.Location = New-Object System.Drawing.Point(16, 128)
    $cbClip.Width = 420
    $cbClip.Checked = [bool](Get-ConfigValue "clipboard_watch" $false)
    $sf.Controls.Add($cbClip)

    $lblDir = New-Object System.Windows.Forms.Label
    $lblDir.Text = "Download folder:"
    $lblDir.Location = New-Object System.Drawing.Point(16, 162)
    $lblDir.Width = 200
    $sf.Controls.Add($lblDir)

    $tbDir = New-Object System.Windows.Forms.TextBox
    $tbDir.Location = New-Object System.Drawing.Point(16, 182)
    $tbDir.Width = 340
    $tbDir.Text = [string](Get-ConfigValue "output_dir" (Join-Path $env:USERPROFILE "Music\SoniQ"))
    $sf.Controls.Add($tbDir)

    $btnBrowse = New-Object System.Windows.Forms.Button
    $btnBrowse.Text = "Browse..."
    $btnBrowse.Location = New-Object System.Drawing.Point(362, 181)
    $btnBrowse.Width = 80
    $btnBrowse.Add_Click({
        $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
        $dlg.Description = "Choose where SoniQ saves your songs"
        if (Test-Path $tbDir.Text) { $dlg.SelectedPath = $tbDir.Text }
        $script:suppressDeactivate = $true
        if ($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { $tbDir.Text = $dlg.SelectedPath }
        $script:suppressDeactivate = $false
    })
    $sf.Controls.Add($btnBrowse)

    $btnOpenDl = New-Object System.Windows.Forms.Button
    $btnOpenDl.Text = "Open downloads"
    $btnOpenDl.Location = New-Object System.Drawing.Point(16, 222)
    $btnOpenDl.Width = 120
    $btnOpenDl.Add_Click({ Start-Process explorer.exe (Get-DownloadDir) })
    $sf.Controls.Add($btnOpenDl)

    $btnOpenLog = New-Object System.Windows.Forms.Button
    $btnOpenLog.Text = "Open logs"
    $btnOpenLog.Location = New-Object System.Drawing.Point(144, 222)
    $btnOpenLog.Width = 100
    $btnOpenLog.Add_Click({
        $logDir = Join-Path $env:USERPROFILE ".soniq\logs"
        if (-not (Test-Path $logDir)) { $null = New-Item -ItemType Directory -Path $logDir }
        Start-Process explorer.exe $logDir
    })
    $sf.Controls.Add($btnOpenLog)

    $btnOpenCfg = New-Object System.Windows.Forms.Button
    $btnOpenCfg.Text = "Open config"
    $btnOpenCfg.Location = New-Object System.Drawing.Point(252, 222)
    $btnOpenCfg.Width = 100
    $btnOpenCfg.Add_Click({
        $cfgPath = Join-Path $env:USERPROFILE ".soniq\config.json"
        if (Test-Path $cfgPath) {
            Start-Process notepad.exe $cfgPath
        } else {
            Notify "SoniQ" "No config file yet - run a download first." "Info"
        }
    })
    $sf.Controls.Add($btnOpenCfg)

    $btnSave = New-Object System.Windows.Forms.Button
    $btnSave.Text = "Save"
    $btnSave.Location = New-Object System.Drawing.Point(276, 266)
    $btnSave.Width = 80
    $btnSave.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $sf.Controls.Add($btnSave)

    $btnCancel = New-Object System.Windows.Forms.Button
    $btnCancel.Text = "Cancel"
    $btnCancel.Location = New-Object System.Drawing.Point(362, 266)
    $btnCancel.Width = 80
    $btnCancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $sf.Controls.Add($btnCancel)

    $sf.AcceptButton = $btnSave
    $sf.CancelButton = $btnCancel

    $script:suppressDeactivate = $true
    $result = $sf.ShowDialog()
    $script:suppressDeactivate = $false
    if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
        try { Set-Autostart $cbAutostart.Checked } catch { }
        Save-SoniqConfig @{
            "close_to_tray" = [bool]$cbClose.Checked
            "check_for_updates" = [bool]$cbUpdates.Checked
            "notifications" = [bool]$cbNotify.Checked
            "clipboard_watch" = [bool]$cbClip.Checked
            "output_dir" = $tbDir.Text.Trim()
            "output_dir_chosen" = $true
        }
        $script:closeToTray = [bool]$cbClose.Checked
        $script:notifications = [bool]$cbNotify.Checked
        $script:clipboardWatch = [bool]$cbClip.Checked
        Notify "SoniQ" "Settings saved." "Info"
    }
    $sf.Dispose()
}

$script:closeToTray = [bool](Get-ConfigValue "close_to_tray" $true)
$script:notifications = [bool](Get-ConfigValue "notifications" $true)
$script:clipboardWatch = [bool](Get-ConfigValue "clipboard_watch" $false)

# ---------------------------------------------------------------------------
# Tray menu + events
# ---------------------------------------------------------------------------

$menu = New-Object System.Windows.Forms.ContextMenuStrip
$miOpen = $menu.Items.Add("Open SoniQ")
$miDownloads = $menu.Items.Add("Open downloads folder")
$miLog = $menu.Items.Add("Open log folder")
$miSettings = $menu.Items.Add("Settings...")
$null = $menu.Items.Add("-")
$miAutostart = $menu.Items.Add("Start with Windows")
$miAutostart.CheckOnClick = $true
$miAutostart.Checked = Test-Path (Get-StartupLinkPath)
$null = $menu.Items.Add("-")
$miQuit = $menu.Items.Add("Quit")
$tray.ContextMenuStrip = $menu

$miOpen.Add_Click({ Show-SoniqMini })
$miDownloads.Add_Click({ Start-Process explorer.exe (Get-DownloadDir) })
$miLog.Add_Click({
    $logDir = Join-Path $Root "logs"
    if (-not (Test-Path $logDir)) { $null = New-Item -ItemType Directory -Path $logDir }
    Start-Process explorer.exe $logDir
})
$miSettings.Add_Click({ Show-SoniqSettings })
$miAutostart.Add_Click({
    try {
        Set-Autostart $miAutostart.Checked
        $msg = if ($miAutostart.Checked) { "SoniQ Tray will start with Windows." } else { "SoniQ Tray will no longer start with Windows." }
        Notify "SoniQ" $msg "Info"
    } catch {
        $miAutostart.Checked = -not $miAutostart.Checked
        Notify "SoniQ" "Could not change the autostart setting." "Error"
    }
})
$miQuit.Add_Click({
    Stop-Worker
    $script:context.ExitThread()
})
# Single click toggles the mini window (with a small delay so a
# double-click can be told apart); double-click opens the SoniQ CLI.
$script:clickTimer = New-Object System.Windows.Forms.Timer
$script:clickTimer.Interval = [System.Windows.Forms.SystemInformation]::DoubleClickTime
$script:clickTimer.Add_Tick({
    $script:clickTimer.Stop()
    if ($form.Visible) {
        $form.Hide()
    } else {
        if (((Get-Date) - $script:lastAutoHide).TotalMilliseconds -lt 500) {
            $script:lastAutoHide = [datetime]::MinValue
        } else {
            Show-SoniqMini
        }
    }
})
$tray.Add_MouseClick({
    param($sender, $eventArgs)
    if ($eventArgs.Button -eq [System.Windows.Forms.MouseButtons]::Left) {
        $script:clickTimer.Stop()
        $script:clickTimer.Start()
    }
})
$tray.Add_MouseDoubleClick({
    param($sender, $eventArgs)
    if ($eventArgs.Button -eq [System.Windows.Forms.MouseButtons]::Left) {
        $script:clickTimer.Stop()
        if ($form.Visible) { $form.Hide() }
        Start-Process -FilePath (Join-Path $Root "app.bat") -WorkingDirectory $Root
    }
})

$tray.Add_BalloonTipClicked({
    if ($script:pendingClipUrl) {
        Send-Command ("/url " + $script:pendingClipUrl)
        $script:pendingClipUrl = $null
        return
    }
    if ($script:lastBalloonFolder) { Start-Process explorer.exe $script:lastBalloonFolder }
})

$script:clipTimer = New-Object System.Windows.Forms.Timer
$script:clipTimer.Interval = 1000
$script:lastClip = ""
$script:clipTimer.Add_Tick({
    if ($form.Visible) {
        $script:transcriptPollTick++
        if ($script:transcriptPollTick -ge 2) {
            $script:transcriptPollTick = 0
            Update-TranscriptView
        }
    }
    if (-not $script:clipboardWatch) { return }
    try {
        $text = [System.Windows.Forms.Clipboard]::GetText()
        if (-not $text -or $text -eq $script:lastClip) { return }
        $script:lastClip = $text
        if ($text -match 'https?://(www\.)?(youtube\.com|youtu\.be)/\S+') {
            $script:pendingClipUrl = $Matches[0]
            Notify "SoniQ" "Copied link - click here to download it" "Info"
        }
    } catch { }
})
$script:clipTimer.Start()

$script:context = New-Object System.Windows.Forms.ApplicationContext
[System.Windows.Forms.Application]::Run($script:context)
Stop-Worker
$tray.Visible = $false
$tray.Dispose()
