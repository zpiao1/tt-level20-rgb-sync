<#
  cleanup-vendor-software.ps1 - MUST RUN AS ADMINISTRATOR.

  Removes everything installed during the keyboard investigation that is no
  longer needed. The keyboard sync does NOT depend on any of it - it talks to
  the device directly over USB HID.

    - TT iTAKE Engine    (never supported this keyboard's PID)
    - Thermaltake Tool
    - PawnIO             (kernel driver; only needed for the SMBus scan)
#>
$ErrorActionPreference = 'Continue'

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($id)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "ERROR: run this from an ELEVATED PowerShell window." -ForegroundColor Red
    Write-Host "  Start menu -> type 'powershell' -> right-click -> Run as administrator"
    exit 1
}

$targets = @(
    @{ Name = 'TT iTAKE Engine'; Exe = 'C:\Program Files\Tt\iTAKE\uninst.exe'; Args = @('/S') },
    @{ Name = 'Thermaltake Tool'; Exe = 'C:\Program Files\Tt\Tool\uninst.exe'; Args = @('/S') },
    @{ Name = 'PawnIO';           Exe = 'C:\Program Files\PawnIO\uninstall.exe'; Args = @('-uninstall') }
)

foreach ($t in $targets) {
    Write-Host "`n=== $($t.Name) ===" -ForegroundColor Cyan
    if (-not (Test-Path $t.Exe)) {
        Write-Host "  already gone (no $($t.Exe))" -ForegroundColor DarkGray
        continue
    }
    Write-Host "  running $($t.Exe) $($t.Args -join ' ')"
    try {
        Start-Process -FilePath $t.Exe -ArgumentList $t.Args -Wait
        Write-Host "  done" -ForegroundColor Green
    } catch {
        Write-Host "  FAILED: $_" -ForegroundColor Red
        Write-Host "  Uninstall '$($t.Name)' manually via Settings > Apps." -ForegroundColor Yellow
    }
}

# Leftover Thermaltake folders/config, only if the uninstallers left them behind.
foreach ($p in @('C:\Program Files\Tt', "$env:APPDATA\Tt")) {
    if (Test-Path $p) {
        Write-Host "`nRemoving leftover: $p"
        Remove-Item $p -Recurse -Force -ErrorAction SilentlyContinue
        if (Test-Path $p) { Write-Host "  still present - remove by hand" -ForegroundColor Yellow }
        else { Write-Host "  removed" -ForegroundColor Green }
    }
}

Write-Host "`nNow re-run the snapshot diff to confirm what is left:" -ForegroundColor Cyan
Write-Host "  powershell -ExecutionPolicy Bypass -File C:\Users\zpiao\tt-keyboard-sync\snapshot.ps1 -Label final"
Write-Host "  powershell -ExecutionPolicy Bypass -File C:\Users\zpiao\tt-keyboard-sync\diff-snapshot.ps1 -From before -To final"
