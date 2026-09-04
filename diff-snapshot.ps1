<#
  diff-snapshot.ps1 - Compare two snapshots to reveal exactly what an install added.
  Usage:  powershell -ExecutionPolicy Bypass -File diff-snapshot.ps1 -From before -To after
  Anything listed as [+] was added and is a candidate for removal during rollback.
#>
param(
    [Parameter(Mandatory=$true)][string]$From,
    [Parameter(Mandatory=$true)][string]$To,
    [switch]$ShowRemoved
)

$ErrorActionPreference = 'SilentlyContinue'
$a = Join-Path $PSScriptRoot "baseline\$From"
$b = Join-Path $PSScriptRoot "baseline\$To"

if (-not (Test-Path $a)) { Write-Error "Missing snapshot: $a"; exit 1 }
if (-not (Test-Path $b)) { Write-Error "Missing snapshot: $b"; exit 1 }

$report = Join-Path $PSScriptRoot "baseline\diff-$From-to-$To.txt"
$out = New-Object System.Collections.ArrayList

function Emit($line) { [void]$out.Add($line); Write-Host $line }

# Warn loudly if the two snapshots were taken at different privilege levels.
function ReadCtx($dir) {
    $f = Join-Path $dir 'context.txt'
    if (Test-Path $f) { return ((Get-Content $f) -join '') } else { return 'elevated=unknown' }
}
$ctxA = ReadCtx $a
$ctxB = ReadCtx $b

Emit "Snapshot diff: $From -> $To"
if ($ctxA -ne $ctxB) {
    Emit ""
    Emit "*** WARNING: privilege mismatch ($From : $ctxA, $To : $ctxB) ***"
    Emit "*** Scheduled tasks, drivers and services will show phantom additions. ***"
    Emit "*** Re-take both snapshots at the same privilege level for a clean diff. ***"
}
Emit ("Generated: " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
Emit ("=" * 70)

$anyChange = $false
foreach ($file in (Get-ChildItem $a -Filter *.txt | Sort-Object Name)) {
    $old = Get-Content (Join-Path $a $file.Name)
    $newPath = Join-Path $b $file.Name
    if (-not (Test-Path $newPath)) { continue }
    $new = Get-Content $newPath

    $added   = Compare-Object $old $new | Where-Object { $_.SideIndicator -eq '=>' } | Select-Object -ExpandProperty InputObject
    $removed = Compare-Object $old $new | Where-Object { $_.SideIndicator -eq '<=' } | Select-Object -ExpandProperty InputObject

    if ($added -or ($ShowRemoved -and $removed)) {
        $anyChange = $true
        Emit ""
        Emit ("### " + $file.BaseName)
        foreach ($x in $added)   { Emit "  [+] $x" }
        if ($ShowRemoved) { foreach ($x in $removed) { Emit "  [-] $x" } }
    }
}

if (-not $anyChange) { Emit ""; Emit "No additions detected." }

$out | Out-File -FilePath $report -Encoding utf8
Write-Host ""
Write-Host "Report saved: $report"
