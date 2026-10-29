# Create a Desktop shortcut to ScamShield AI with the project's own icon.
# Run through setup_desktop.bat, or: powershell -ExecutionPolicy Bypass -File tools\create_shortcut.ps1

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $root "launcher.py"
$icon = Join-Path $root "assets\icon.ico"

if (-not (Test-Path $launcher)) {
    throw "launcher.py was not found next to tools\. Put this script back inside the project folder."
}
if (-not (Test-Path $icon)) {
    throw "assets\icon.ico is missing. Run: python tools\make_logo.py"
}

# Prefer the project virtualenv, then whatever pythonw is on PATH, then plain python.
$pythonw = Join-Path $root ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    $command = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if ($command) {
        $pythonw = $command.Source
    } else {
        $command = Get-Command python.exe -ErrorAction SilentlyContinue
        if (-not $command) {
            throw "Python was not found on PATH. Install Python 3.10+ and try again."
        }
        $pythonw = $command.Source
    }
}

$desktop = [Environment]::GetFolderPath("Desktop")
$linkPath = Join-Path $desktop "ScamShield AI.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($linkPath)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = '"' + $launcher + '"'
$shortcut.WorkingDirectory = $root
$shortcut.IconLocation = "$icon,0"
$shortcut.Description = "ScamShield AI - offline job scam detector"
$shortcut.WindowStyle = 7
$shortcut.Save()

Write-Host "Created: $linkPath"
Write-Host "Target:  $pythonw `"$launcher`""
Write-Host "Icon:    $icon"
