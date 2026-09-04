<#
  detect-rgb.ps1 - MUST RUN AS ADMINISTRATOR.
  Runs OpenRGB device detection with SMBus access and prints what it found.
#>
$ErrorActionPreference = 'Continue'

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($id)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "ERROR: run this from an ELEVATED PowerShell window." -ForegroundColor Red
    Write-Host "  Start menu -> type 'powershell' -> right-click -> Run as administrator"
    exit 1
}

$exe = "C:\Users\zpiao\openrgb-portable\OpenRGB Windows 64-bit\OpenRGB.exe"
if (-not (Test-Path $exe)) { Write-Host "OpenRGB not found at $exe" -ForegroundColor Red; exit 1 }

Write-Host "Running OpenRGB detection (elevated)..." -ForegroundColor Cyan
$before = Get-Date
Start-Process -FilePath $exe -ArgumentList '--list-devices' -Wait -WindowStyle Hidden

$logDir = Join-Path $env:APPDATA 'OpenRGB\logs'
$log = Get-ChildItem $logDir -Filter *.log |
       Where-Object { $_.LastWriteTime -ge $before.AddSeconds(-5) } |
       Sort-Object LastWriteTime -Descending | Select-Object -First 1

if (-not $log) { Write-Host "No new log produced." -ForegroundColor Yellow; exit 1 }

Write-Host "`n--- SMBus / I2C initialisation ---" -ForegroundColor Cyan
Select-String -Path $log.FullName -Pattern 'PawnIO|Registering I2C|Permission|aborted' |
    ForEach-Object { "  " + $_.Line }

Write-Host "`n--- Devices found ---" -ForegroundColor Cyan
$found = Select-String -Path $log.FullName -Pattern 'Found a|Detecting .* devices|controller|Polychrome|ENE|DRAM|Aura|detected'
if ($found) { $found | ForEach-Object { "  " + $_.Line } } else { Write-Host "  (none reported)" }

Write-Host "`nFull log: $($log.FullName)" -ForegroundColor DarkGray
