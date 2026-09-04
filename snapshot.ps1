<#
  snapshot.ps1 - Capture system state so a later install can be diffed and cleanly reversed.
  Usage:  powershell -ExecutionPolicy Bypass -File snapshot.ps1 -Label before
  Writes one file per category into .\baseline\<label>\
#>
param(
    [Parameter(Mandatory=$true)][string]$Label
)

$ErrorActionPreference = 'SilentlyContinue'
$root = Join-Path $PSScriptRoot "baseline\$Label"
New-Item -ItemType Directory -Force -Path $root | Out-Null

function Save($name, $data) {
    $path = Join-Path $root "$name.txt"
    $data | Out-File -FilePath $path -Encoding utf8
    Write-Host ("  {0,-22} {1,6} lines" -f $name, (@($data).Count))
}

# Record privilege level. Get-ScheduledTask and some driver/service queries
# return more rows when elevated, so diffing an elevated snapshot against an
# unelevated one invents dozens of phantom additions.
$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
"elevated=$isAdmin" | Out-File -FilePath (Join-Path $root 'context.txt') -Encoding utf8

Write-Host "Snapshot '$Label' -> $root   (elevated: $isAdmin)"

# Installed programs across all three uninstall hives
$hives = @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*'
)
Save 'programs' (Get-ItemProperty $hives |
    Where-Object { $_.DisplayName } |
    ForEach-Object { "$($_.DisplayName)|$($_.DisplayVersion)|$($_.Publisher)|$($_.UninstallString)" } |
    Sort-Object -Unique)

Save 'services' (Get-Service | ForEach-Object { "$($_.Name)|$($_.StartType)|$($_.Status)" } | Sort-Object)

Save 'drivers' (Get-CimInstance Win32_SystemDriver |
    ForEach-Object { "$($_.Name)|$($_.State)|$($_.PathName)" } | Sort-Object)

Save 'tasks' (Get-ScheduledTask | ForEach-Object { "$($_.TaskPath)$($_.TaskName)|$($_.State)" } | Sort-Object)

# Autostart entries
$runKeys = @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run',
    'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run',
    'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run'
)
$autoruns = foreach ($k in $runKeys) {
    $item = Get-Item $k
    if ($item) {
        foreach ($v in $item.GetValueNames()) { "$k\$v = $($item.GetValue($v))" }
    }
}
$startupDirs = @(
    "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup",
    "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\Startup"
)
$autoruns += foreach ($d in $startupDirs) { Get-ChildItem $d -File | ForEach-Object { "STARTUP-FOLDER: $($_.FullName)" } }
Save 'autoruns' ($autoruns | Sort-Object)

# Top-level directory listings - catches leftover folders
$dirs = @{
    'dirs_programfiles'    = $env:ProgramFiles
    'dirs_programfilesx86' = ${env:ProgramFiles(x86)}
    'dirs_programdata'     = $env:ProgramData
    'dirs_localappdata'    = $env:LOCALAPPDATA
    'dirs_roamingappdata'  = $env:APPDATA
}
foreach ($d in $dirs.GetEnumerator()) {
    Save $d.Key (Get-ChildItem $d.Value -Directory | Select-Object -ExpandProperty Name | Sort-Object)
}

# Registry software keys - catches leftover registry branches
$regRoots = @{
    'reg_hklm_software' = 'HKLM:\SOFTWARE'
    'reg_hklm_wow6432'  = 'HKLM:\SOFTWARE\WOW6432Node'
    'reg_hkcu_software' = 'HKCU:\SOFTWARE'
}
foreach ($r in $regRoots.GetEnumerator()) {
    Save $r.Key (Get-ChildItem $r.Value | Select-Object -ExpandProperty PSChildName | Sort-Object)
}

Save 'listening_ports' (Get-NetTCPConnection -State Listen |
    ForEach-Object { "$($_.LocalAddress):$($_.LocalPort)|$((Get-Process -Id $_.OwningProcess).ProcessName)" } |
    Sort-Object -Unique)

Write-Host "Done."
