<#
  cleanup-residue.ps1 - MUST RUN AS ADMINISTRATOR.

  Removes what the Razer and Thermaltake uninstallers left behind. Every item
  below was verified to be vendor residue, not shared or system state.
  Nothing here is used by the keyboard sync.
#>
$ErrorActionPreference = 'Continue'

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "ERROR: run this from an ELEVATED PowerShell window." -ForegroundColor Red
    exit 1
}

$folders = @(
    'C:\Program Files (x86)\Tt',          # empty
    'C:\Program Files\Razer',             # empty
    'C:\Program Files (x86)\Razer',       # empty
    "$env:LOCALAPPDATA\Razer",            # empty
    "$env:ProgramData\Razer"              # one stale log file
)

$regKeys = @(
    'HKCU:\SOFTWARE\Razer',
    'HKCU:\SOFTWARE\Thermaltake',                    # TT RGB PLUS settings
    'HKLM:\SOFTWARE\Razer',                          # Razer\Services
    'HKLM:\SOFTWARE\Thermaltake',                    # TT RGB PLUS
    'HKLM:\SOFTWARE\WOW6432Node\Razer',              # Razer\Services
    'HKLM:\SOFTWARE\WOW6432Node\WOW6432Node',        # nested Razer\Services\GMS3
    'HKLM:\SOFTWARE\WYVRN'                           # Razer developer platform
)

# Orphaned Add/Remove entry: the program is gone but the entry survived because
# its uninstaller had already been removed when the folder was deleted.
$orphanEntries = @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\TT iTAKE Engine'
)

Write-Host "=== Folders ===" -ForegroundColor Cyan
foreach ($f in $folders) {
    if (Test-Path $f) {
        Remove-Item $f -Recurse -Force -ErrorAction SilentlyContinue
        if (Test-Path $f) { Write-Host "  STILL PRESENT: $f" -ForegroundColor Yellow }
        else { Write-Host "  removed: $f" -ForegroundColor Green }
    } else { Write-Host "  already gone: $f" -ForegroundColor DarkGray }
}

Write-Host "`n=== Registry ===" -ForegroundColor Cyan
foreach ($k in $regKeys + $orphanEntries) {
    if (Test-Path $k) {
        Remove-Item $k -Recurse -Force -ErrorAction SilentlyContinue
        if (Test-Path $k) { Write-Host "  STILL PRESENT: $k" -ForegroundColor Yellow }
        else { Write-Host "  removed: $k" -ForegroundColor Green }
    } else { Write-Host "  already gone: $k" -ForegroundColor DarkGray }
}

Write-Host "`n=== Left alone deliberately ===" -ForegroundColor Cyan
Write-Host "  LAV Filters 0.74.1  - a working codec pack bundled by TT RGB PLUS."
Write-Host "                        Not residue. Remove via Settings > Apps if unwanted."
Write-Host "  HKCU\SOFTWARE\HWiNFO64 - settings key from TT's bundled HWiNFO. Harmless."
Write-Host "  PawnIO driver package  - uninstalled; the inert DriverStore copy clears on reboot."
Write-Host "  HWiNFO_170 driver      - loaded from Temp by the old TT software; clears on reboot."

Write-Host "`nReboot to clear the two stale drivers, then verify with:" -ForegroundColor Cyan
Write-Host "  snapshot.ps1 -Label verify   (run ELEVATED, same as 'final')"
Write-Host "  diff-snapshot.ps1 -From final -To verify"
