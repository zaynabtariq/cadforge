<powershell>
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$root = 'C:\FusionWorkstation'
New-Item -ItemType Directory -Force $root | Out-Null
Start-Transcript -Path "$root\bootstrap.log" -Append
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest 'https://d1uj6qtbmh3dt5.cloudfront.net/2025.0/Servers/nice-dcv-server-x64-Release-2025.0-20103.msi' -OutFile "$root\dcv.msi"
    $signature = Get-AuthenticodeSignature "$root\dcv.msi"
    if ($signature.Status -ne 'Valid') { throw "Invalid DCV installer signature: $($signature.Status)" }
    $p = Start-Process msiexec.exe -ArgumentList "/i $root\dcv.msi /quiet /norestart AUTOMATIC_SESSION_OWNER=Administrator /l*v $root\dcv-install.log" -Wait -PassThru
    if ($p.ExitCode -notin @(0,3010)) { throw "DCV installer exit: $($p.ExitCode)" }
    powercfg /change monitor-timeout-ac 0
    powercfg /change standby-timeout-ac 0
    'DCV installed' | Set-Content "$root\status.txt"
    Invoke-WebRequest 'https://dl.appstreaming.autodesk.com/production/installers/Fusion%20Client%20Downloader.exe' -OutFile "$root\FusionClientDownloader.exe"
    $signature = Get-AuthenticodeSignature "$root\FusionClientDownloader.exe"
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Autodesk') { throw 'Invalid Autodesk installer signature' }
    'Installing Fusion' | Set-Content "$root\status.txt"
    $p = Start-Process "$root\FusionClientDownloader.exe" -ArgumentList '--globalinstall --quiet' -Wait -PassThru
    "Fusion installer exit: $($p.ExitCode)" | Set-Content "$root\status.txt"
    if ($p.ExitCode -ne 0) { throw "Fusion installer exit: $($p.ExitCode)" }
    $launchScript = @'
$shortcut = Get-ChildItem 'C:\Users\Public\Desktop','C:\ProgramData\Microsoft\Windows\Start Menu\Programs' -Filter '*Fusion*.lnk' -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.Name -notmatch 'Service|Uninstall' } | Select-Object -First 1
if ($shortcut) { Start-Process $shortcut.FullName } else {
    $fusion = Get-ChildItem 'C:\Program Files\Autodesk\webdeploy\production' -Filter Fusion360.exe -Recurse -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($fusion) { Start-Process $fusion.FullName }
}
'@
    Set-Content "$root\Start-Fusion.ps1" $launchScript
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut('C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Startup\Fusion.lnk')
    $shortcut.TargetPath = 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
    $shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File C:\FusionWorkstation\Start-Fusion.ps1'
    $shortcut.Save()
    'Ready for desktop sign-in' | Set-Content "$root\status.txt"
} catch {
    $_ | Out-String | Set-Content "$root\error.txt"
    throw
} finally { Stop-Transcript }
</powershell>
