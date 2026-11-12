# Create a desktop shortcut with a custom icon.
# ASCII-only on purpose: safe under Windows PowerShell 5.1 regardless of codepage.
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$bat  = Get-ChildItem -LiteralPath $root -Filter *.bat | Select-Object -First 1
$icon = Get-ChildItem -LiteralPath $root -Filter *.ico | Select-Object -First 1

if (-not $bat) {
    Write-Host "Launcher .bat not found in: $root" -ForegroundColor Red
    exit 1
}

$desktop = [Environment]::GetFolderPath("Desktop")

# "Yixin / LocalTranslate" written with code points so this file stays ASCII-only.
$label = -join ([char]0x8BD1, [char]0x5FC3, ' ', [char]0x00B7, ' ', `
                [char]0x672C, [char]0x5730, [char]0x7FFB, [char]0x8BD1, `
                [char]0x52A9, [char]0x624B)
$lnk = Join-Path $desktop ($label + ".lnk")

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($lnk)
$shortcut.TargetPath = $bat.FullName
$shortcut.WorkingDirectory = $root
if ($icon) {
    $shortcut.IconLocation = $icon.FullName
}
$shortcut.WindowStyle = 7
$shortcut.Description = $label
$shortcut.Save()

Write-Host "Shortcut created:" -ForegroundColor Green
Write-Host "  $lnk"
