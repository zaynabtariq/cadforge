param([Parameter(Mandatory=$true)][string]$OperatorAddress)
$ErrorActionPreference='Stop'
$cap=Get-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
if ($cap.State -ne 'Installed') { Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 | Out-Null }
Set-Service sshd -StartupType Automatic
$sshDir='C:\Users\Fusion\.ssh'
New-Item $sshDir -ItemType Directory -Force | Out-Null
Set-Content "$sshDir\authorized_keys" '__PUBLIC_KEY__' -Encoding ascii
icacls $sshDir /inheritance:r /grant:r 'Fusion:(OI)(CI)F' 'SYSTEM:(OI)(CI)F' 'Administrators:(OI)(CI)F' | Out-Null
icacls "$sshDir\authorized_keys" /inheritance:r /grant:r 'Fusion:F' 'SYSTEM:F' 'Administrators:F' | Out-Null
icacls $sshDir /setowner Fusion /T | Out-Null
Start-Service sshd
$config='C:\ProgramData\ssh\sshd_config'
Copy-Item $config "$config.before-fusion" -Force
@'
Port 22
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
AllowUsers fusion
AuthorizedKeysFile .ssh/authorized_keys
AllowTcpForwarding local
GatewayPorts no
PermitOpen 127.0.0.1:8080 localhost:8080
Subsystem sftp sftp-server.exe
'@ | Set-Content $config -Encoding ascii
& 'C:\Windows\System32\OpenSSH\sshd.exe' -t
if ($LASTEXITCODE -ne 0) { throw 'sshd config validation failed' }
New-ItemProperty -Path 'HKLM:\SOFTWARE\OpenSSH' -Name DefaultShell -Value 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -PropertyType String -Force | Out-Null
if (-not (Get-NetFirewallRule -Name OpenSSH-Server-In-TCP -ErrorAction SilentlyContinue)) { New-NetFirewallRule -Name OpenSSH-Server-In-TCP -DisplayName 'OpenSSH Server' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 | Out-Null }
Set-NetFirewallRule -Name OpenSSH-Server-In-TCP -Enabled True -Profile Any -RemoteAddress $OperatorAddress
Restart-Service sshd
Get-Service sshd | Select-Object Name,Status | ConvertTo-Json
Get-Content 'C:\ProgramData\ssh\ssh_host_ed25519_key.pub'
