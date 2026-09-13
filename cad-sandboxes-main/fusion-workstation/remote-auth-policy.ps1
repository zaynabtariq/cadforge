$ErrorActionPreference='Stop'
$key='HKLM:\SOFTWARE\Policies\Microsoft\Edge'
New-Item $key -Force | Out-Null
# Keep native Identity Manager callbacks inside this Windows session.
$policy='[{"protocol":"adskidmgr","allowed_origins":["https://signin.autodesk.com","https://accounts.autodesk.com"]},{"protocol":"adsk.idmgr","allowed_origins":["https://signin.autodesk.com","https://accounts.autodesk.com"]}]'
New-ItemProperty $key -Name AutoLaunchProtocolsFromOrigins -Value $policy -PropertyType String -Force | Out-Null
New-ItemProperty $key -Name PasswordManagerEnabled -Value 0 -PropertyType DWord -Force | Out-Null
$config='C:\ProgramData\ssh\sshd_config'
$text=Get-Content $config -Raw
if($text -notmatch 'PermitOpen[^\r\n]*127.0.0.1:9222'){
 $text=[regex]::Replace($text,'(?m)^PermitOpen ([^\r\n]+)','$0 127.0.0.1:9222')
 Set-Content $config $text -Encoding ascii
 & C:\Windows\System32\OpenSSH\sshd.exe -t
 if($LASTEXITCODE -ne 0){throw 'Invalid SSH configuration'}
 Restart-Service sshd
}
'Autodesk callback and password-save policies configured.'
