$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$root='C:\FusionWorkstation'
$auth=Join-Path $root 'Auth'
New-Item $auth -ItemType Directory -Force | Out-Null
if (Get-LocalUser FusionAuth -ErrorAction SilentlyContinue) {throw 'Fresh auth user already exists; inspect instead of resetting'}
Get-ScheduledTask -TaskName 'FusionWorkstation-*' | Disable-ScheduledTask | Out-Null
Get-Process Fusion360,AdskIdentityManager -ErrorAction SilentlyContinue | Stop-Process -Force
$bytes=New-Object byte[] 32
$rng=[Security.Cryptography.RandomNumberGenerator]::Create();$rng.GetBytes($bytes);$rng.Dispose()
$password=[Convert]::ToBase64String($bytes)+'aA1!'
New-LocalUser FusionAuth -Password (ConvertTo-SecureString $password -AsPlainText -Force) -PasswordNeverExpires -UserMayNotChangePassword | Out-Null
Add-LocalGroupMember -Group Users -Member FusionAuth -ErrorAction SilentlyContinue
& "$root\Autologon\Autologon64.exe" /accepteula FusionAuth $env:COMPUTERNAME $password | Out-Null
$password=$null;[Array]::Clear($bytes,0,$bytes.Length)
Disable-LocalUser Fusion

# Use the installed native browser. The broker reads only its sign-in URL
# through loopback CDP over an SSH command; CDP is never publicly forwarded.
$edge='C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
if(!(Test-Path $edge)){throw 'Microsoft Edge is required for desktop sign-in'}
$command='"'+$edge+'" --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 --user-data-dir="C:\Users\FusionAuth\AppData\Local\FusionWorkstation\EdgeAuth" --no-first-run --no-default-browser-check "%1"'
Set-Item 'HKLM:\SOFTWARE\Classes\MSEdgeHTM\shell\open\command' -Value $command
'<?xml version="1.0" encoding="UTF-8"?><DefaultAssociations><Association Identifier="http" ProgId="MSEdgeHTM" ApplicationName="Microsoft Edge"/><Association Identifier="https" ProgId="MSEdgeHTM" ApplicationName="Microsoft Edge"/></DefaultAssociations>' | Set-Content "$auth\defaults.xml" -Encoding UTF8
& dism.exe /Online "/Import-DefaultAppAssociations:$auth\defaults.xml" | Out-Null
if($LASTEXITCODE -ne 0){throw 'Default browser registration failed'}
New-Item 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\System' -Force | Out-Null
New-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\System' -Name DefaultAssociationsConfiguration -Value "$auth\defaults.xml" -Force | Out-Null

$startup=@'
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$root='C:\FusionWorkstation'
$local=Join-Path $env:LOCALAPPDATA 'FusionWorkstation\Auth'
New-Item $local -ItemType Directory -Force | Out-Null
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
icacls $local /inheritance:r /grant:r "*${sid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' | Out-Null
$addin=Join-Path $env:APPDATA 'Autodesk\Autodesk Fusion 360\API\AddIns'
New-Item $addin -ItemType Directory -Force | Out-Null
Expand-Archive "$root\Auth\bridge-package.zip" $addin -Force
$ssh=Join-Path $env:USERPROFILE '.ssh'
New-Item $ssh -ItemType Directory -Force | Out-Null
Copy-Item "$root\Auth\authorized_keys" "$ssh\authorized_keys" -Force
icacls $ssh /inheritance:r /grant:r "*${sid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' | Out-Null
$identity=Join-Path $env:LOCALAPPDATA 'Autodesk\Identity Services\idservices.db'
if(!(Test-Path "$local\fresh-profile.json")) {
 @{user=$env:USERNAME;identity_cache_present=(Test-Path $identity);created_utc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content "$local\fresh-profile.json"
}
# Drain desktop callbacks only in this interactive session. Content remains
# DPAPI encrypted at rest and is never placed in scripts or SSM commands.
Add-Type -AssemblyName System.Security
$exe=Get-ChildItem 'C:\Program Files\Autodesk\webdeploy\production' -Directory | ForEach-Object {Join-Path $_.FullName 'Fusion360.exe'} | Where-Object {Test-Path $_} | Select-Object -First 1
$fusionProcess=Start-Process $exe -WorkingDirectory (Split-Path $exe) -PassThru
$fusionProcess.PriorityClass='Normal'
Start-Process powershell.exe -WindowStyle Hidden -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File C:\FusionWorkstation\Auth\Begin-SignIn.ps1'
Start-Process powershell.exe -WindowStyle Hidden -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File C:\FusionWorkstation\Auth\Dismiss-FirstRun.ps1'
while($true){
 $path=Join-Path $local 'callback.dpapi'
 if(Test-Path $path){
  try {
   $encrypted=[IO.File]::ReadAllBytes($path);Remove-Item $path -Force
   $bytes=[Security.Cryptography.ProtectedData]::Unprotect($encrypted,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
   $callback=[Text.Encoding]::UTF8.GetString($bytes)
   $uri=[Uri]$callback
   if($uri.Scheme -eq 'adskidmgr' -and $callback.Length -lt 16384){Start-Process $callback}
   [Array]::Clear($bytes,0,$bytes.Length);$callback=$null
  } catch { 'callback_failed' | Set-Content (Join-Path $local 'status.txt') }
 }
 Start-Sleep -Milliseconds 250
}
'@
$startup | Set-Content "$auth\Start-AuthFusion.ps1"
Copy-Item 'C:\Users\Fusion\.ssh\authorized_keys' "$auth\authorized_keys"
icacls $auth /grant 'FusionAuth:(OI)(CI)RX' | Out-Null
$principal=New-ScheduledTaskPrincipal -UserId "$env:COMPUTERNAME\FusionAuth" -LogonType Interactive -RunLevel Limited
$action=New-ScheduledTaskAction -Execute powershell.exe -Argument '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File C:\FusionWorkstation\Auth\Start-AuthFusion.ps1'
$trigger=New-ScheduledTaskTrigger -AtLogOn -User "$env:COMPUTERNAME\FusionAuth"
$settings=New-ScheduledTaskSettingsSet -Priority 4 -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable
$begin=New-ScheduledTaskAction -Execute powershell.exe -Argument '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File C:\FusionWorkstation\Auth\Begin-SignIn.ps1'
Register-ScheduledTask -TaskName FusionAuth-BeginSignIn -Principal $principal -Action $begin -Settings $settings -Force | Out-Null
Register-ScheduledTask -TaskName FusionAuth-Session -Principal $principal -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
$config='C:\ProgramData\ssh\sshd_config'
(Get-Content $config -Raw).Replace('AllowUsers fusion','AllowUsers fusionauth') | Set-Content $config -Encoding ascii
Stop-Service sshd
Get-ChildItem 'C:\ProgramData\ssh\ssh_host_*' | Remove-Item -Force
& 'C:\Windows\System32\OpenSSH\ssh-keygen.exe' -A 2>$null
Start-Service sshd
Get-Content 'C:\ProgramData\ssh\ssh_host_ed25519_key.pub'
'Fresh FusionAuth profile configured; reboot required.'
