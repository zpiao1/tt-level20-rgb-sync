<#
  make-restore-point.ps1 - MUST RUN AS ADMINISTRATOR.
  Enables System Restore on C: (currently disabled - you have zero restore points)
  and creates a named checkpoint you can roll back to.
#>
$ErrorActionPreference = 'Stop'

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($id)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "This script must be run from an ELEVATED PowerShell window."
    exit 1
}

Write-Host "Enabling System Restore on C:\ ..."
Enable-ComputerRestore -Drive "C:\"

# Windows throttles checkpoints to one per 24h by default; lift it for this run.
$srKey = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\SystemRestore'
$prev = (Get-ItemProperty $srKey -Name SystemRestorePointCreationFrequency -ErrorAction SilentlyContinue).SystemRestorePointCreationFrequency
Set-ItemProperty $srKey -Name SystemRestorePointCreationFrequency -Value 0 -Type DWord

Write-Host "Reserving shadow-copy space (5% of C:) ..."
vssadmin resize shadowstorage /for=C: /on=C: /maxsize=5%

Write-Host "Creating restore point 'Before Chroma RGB install' ..."
Checkpoint-Computer -Description "Before Chroma RGB install" -RestorePointType MODIFY_SETTINGS

# Restore the original throttle setting
if ($null -ne $prev) {
    Set-ItemProperty $srKey -Name SystemRestorePointCreationFrequency -Value $prev -Type DWord
} else {
    Remove-ItemProperty $srKey -Name SystemRestorePointCreationFrequency -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "Restore points now on this system:"
Get-ComputerRestorePoint | Select-Object SequenceNumber, Description, CreationTime | Format-Table -AutoSize
