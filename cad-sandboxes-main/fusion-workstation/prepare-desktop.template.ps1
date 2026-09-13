$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root='C:\FusionWorkstation'
if (Get-LocalUser -Name Fusion -ErrorAction SilentlyContinue) { throw 'Fusion user already exists; refusing to rotate credentials implicitly' }
Invoke-WebRequest 'https://download.sysinternals.com/files/AutoLogon.zip' -OutFile "$root\Autologon.zip"
Expand-Archive "$root\Autologon.zip" "$root\Autologon" -Force
$sig=Get-AuthenticodeSignature "$root\Autologon\Autologon64.exe"
if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch 'Microsoft') { throw 'Invalid Autologon signature' }
$bytes=New-Object byte[] 32
$rng=[Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
$password=[Convert]::ToBase64String($bytes)+'aA1!'
New-LocalUser -Name Fusion -Password (ConvertTo-SecureString $password -AsPlainText -Force) -FullName 'Fusion Workstation' -PasswordNeverExpires -UserMayNotChangePassword | Out-Null
Add-LocalGroupMember -Group 'Users' -Member Fusion -ErrorAction SilentlyContinue
Add-LocalGroupMember -Group 'Remote Desktop Users' -Member Fusion
& "$root\Autologon\Autologon64.exe" /accepteula Fusion $env:COMPUTERNAME $password | Out-Null
$rsa=New-Object Security.Cryptography.RSACryptoServiceProvider
$rsa.FromXmlString('__PUBLIC_KEY__')
$encrypted=[Convert]::ToBase64String($rsa.Encrypt([Text.Encoding]::UTF8.GetBytes($password),$true))
Set-Content "$root\desktop-password.encrypted" $encrypted
$password=$null
Write-Output 'Dedicated Fusion user and encrypted automatic logon configured.'
Write-Output "ENCRYPTED_PASSWORD=$encrypted"
