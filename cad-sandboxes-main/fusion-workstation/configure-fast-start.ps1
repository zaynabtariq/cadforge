$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$root='C:\FusionWorkstation'
$source=Join-Path $root 'User\Start-Fusion.fast.ps1'
if (!(Test-Path "$root\Start-Fusion.original.ps1")) { Copy-Item "$root\Start-Fusion.ps1" "$root\Start-Fusion.original.ps1" }
Copy-Item $source "$root\Start-Fusion.ps1" -Force
New-Item "$root\StartupBackup" -ItemType Directory -Force | Out-Null
$shortcut='C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Startup\Fusion.lnk'
if (Test-Path $shortcut) { Move-Item $shortcut "$root\StartupBackup\Fusion.lnk" -Force }
$action=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File C:\FusionWorkstation\Start-Fusion.ps1'
$principal=New-ScheduledTaskPrincipal -UserId "$env:COMPUTERNAME\Fusion" -LogonType Interactive -RunLevel Limited
$logon=New-ScheduledTaskTrigger -AtLogOn -User "$env:COMPUTERNAME\Fusion"
$recovery=New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
$settings=New-ScheduledTaskSettingsSet -Priority 4 -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 2) -StartWhenAvailable
$logonAction=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File C:\FusionWorkstation\Start-Fusion.ps1 -ResetRecoveryWindow'
Register-ScheduledTask -TaskName 'FusionWorkstation-AutoStart' -Action $logonAction -Principal $principal -Trigger $logon -Settings $settings -Force | Out-Null
Register-ScheduledTask -TaskName 'FusionWorkstation-Recover' -Action $action -Principal $principal -Trigger $recovery -Settings $settings -Force | Out-Null
# No sleep/display power saving in the dedicated console workstation.
powercfg /change monitor-timeout-ac 0
powercfg /change standby-timeout-ac 0
Write-Output 'Immediate logon launch and bounded process-exit recovery configured. No running Fusion process was terminated.'
