$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$archive='C:\FusionWorkstation\User\bridge-package.zip'
$expected='1f7e4b38e6d553557799995705356c10f19cd6bd0fd1d94ab1761893a68d01e6'
if ((Get-FileHash $archive -Algorithm SHA256).Hash.ToLower() -ne $expected) { throw 'Package checksum mismatch' }
$parent=Join-Path $env:APPDATA 'Autodesk\Autodesk Fusion 360\API\AddIns'
$destination=Join-Path $parent 'FusionMCPBridge'
New-Item $parent -ItemType Directory -Force | Out-Null
if (Test-Path $destination) { Copy-Item $destination "C:\FusionWorkstation\User\BridgeBackup-$(Get-Date -Format yyyyMMdd-HHmmss)" -Recurse }
Expand-Archive $archive $parent -Force
$files=Get-ChildItem $destination -File | Where-Object {$_.Extension -in '.py','.manifest'}
[PSCustomObject]@{Destination=$destination;Files=$files.Count;RunOnStartup=[bool](Select-String -Path "$destination\FusionMCPBridge.manifest" -Pattern '"runOnStartup": true')} | ConvertTo-Json
$files | ForEach-Object { [PSCustomObject]@{name=$_.Name;sha256=(Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()} } | ConvertTo-Json | Set-Content C:\FusionWorkstation\User\bridge-installed-hashes.json
