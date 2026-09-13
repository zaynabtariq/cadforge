param([ValidateSet('store','status','self-test','delete')][string]$Mode='status')
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
Add-Type -AssemblyName System.Security
$vault=Join-Path $env:LOCALAPPDATA 'FusionWorkstation\Secrets'
$path=Join-Path $vault 'autodesk.dpapi'
function Protect-Bytes([byte[]]$bytes) { [Security.Cryptography.ProtectedData]::Protect($bytes,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser) }
function Unprotect-Bytes([byte[]]$bytes) { [Security.Cryptography.ProtectedData]::Unprotect($bytes,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser) }
function Prepare-Vault {
 New-Item $vault -ItemType Directory -Force | Out-Null
 $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
 & icacls $vault /inheritance:r /grant:r "*${sid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' | Out-Null
 if ($LASTEXITCODE -ne 0) { throw 'Unable to restrict vault ACL' }
}
try {
 switch ($Mode) {
  'store' {
   # Secret arrives on SSH stdin, never as an argument, environment variable, or SSM payload.
   $inputText=[Console]::In.ReadToEnd()
   if ($inputText.Length -gt 16384) { throw 'Invalid credential payload' }
   $credential=$inputText | ConvertFrom-Json
   if (!$credential.username -or !$credential.password -or $credential.username -isnot [string] -or $credential.password -isnot [string]) { throw 'Invalid credential payload' }
   Prepare-Vault
   $bytes=[Text.Encoding]::UTF8.GetBytes($inputText)
   try { [IO.File]::WriteAllBytes($path,(Protect-Bytes $bytes)) } finally { [Array]::Clear($bytes,0,$bytes.Length);$inputText=$null;$credential=$null }
   @{stored=$true;protection='DPAPI CurrentUser';path=$path} | ConvertTo-Json -Compress
  }
  'status' { @{credential_present=(Test-Path $path);protection='DPAPI CurrentUser'} | ConvertTo-Json -Compress }
  'self-test' {
   Prepare-Vault
   $testPath=Join-Path $vault ('self-test-'+[guid]::NewGuid().ToString()+'.dpapi')
   $bytes=New-Object byte[] 64
   $rng=[Security.Cryptography.RandomNumberGenerator]::Create();$rng.GetBytes($bytes);$rng.Dispose()
   try {
    [IO.File]::WriteAllBytes($testPath,(Protect-Bytes $bytes))
    $decoded=Unprotect-Bytes ([IO.File]::ReadAllBytes($testPath))
    $same=[Convert]::ToBase64String($bytes) -ceq [Convert]::ToBase64String($decoded)
    if (!$same) {throw 'Vault roundtrip failed'}
    @{self_test=$true;credential_present=(Test-Path $path);protection='DPAPI CurrentUser'} | ConvertTo-Json -Compress
   } finally {
    [Array]::Clear($bytes,0,$bytes.Length)
    if ($decoded) {[Array]::Clear($decoded,0,$decoded.Length)}
    Remove-Item $testPath -ErrorAction SilentlyContinue
   }
  }
  'delete' { if (Test-Path $path) {Remove-Item $path}; @{deleted=$true} | ConvertTo-Json -Compress }
 }
} catch {
 # Do not emit PowerShell exception records that might include secret input text.
 [Console]::Error.WriteLine('Credential vault operation failed. No secret was printed.')
 exit 1
}
