param([switch]$ResetRecoveryWindow)
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$root='C:\FusionWorkstation\User'
$log=Join-Path $root 'startup-events.jsonl'
function Write-Event($state,$detail) {
    @{utc=(Get-Date).ToUniversalTime().ToString('o');state=$state;detail=$detail} | ConvertTo-Json -Compress | Add-Content $log
}
if (Get-Process Fusion360 -ErrorAction SilentlyContinue) { exit 0 }
$historyPath=Join-Path $root 'launch-history.json'
$recent=@()
if ($ResetRecoveryWindow -and (Test-Path $historyPath)) { Remove-Item $historyPath }
if (Test-Path $historyPath) { $stored=Get-Content $historyPath -Raw | ConvertFrom-Json; $recent=@($stored | Where-Object {[datetime]$_ -gt (Get-Date).ToUniversalTime().AddMinutes(-15)}) }
if ($recent.Count -ge 3) { Write-Event 'needs_attention' 'Three launch attempts in 15 minutes; automatic recovery paused'; exit 0 }
$cache=Join-Path $root 'fusion-executable.txt'
$exe=if (Test-Path $cache) {(Get-Content $cache -Raw).Trim()} else {$null}
if (!$exe -or !(Test-Path $exe)) {
    $exe=Get-ChildItem 'C:\Program Files\Autodesk\webdeploy\production' -Directory | ForEach-Object {Get-Item (Join-Path $_.FullName 'Fusion360.exe') -ErrorAction SilentlyContinue} | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
    if (!$exe) { Write-Event 'needs_attention' 'Fusion executable not found'; exit 1 }
    Set-Content $cache $exe
}
$recent+=((Get-Date).ToUniversalTime().ToString('o'))
ConvertTo-Json -InputObject @($recent) | Set-Content $historyPath
Write-Event 'launch_requested' $exe
$p=Start-Process $exe -WorkingDirectory (Split-Path $exe) -PassThru
$p.PriorityClass='Normal'
Write-Event 'process_started' @{pid=$p.Id}
