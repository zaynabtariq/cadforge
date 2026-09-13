$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$deadline=(Get-Date).AddMinutes(5)
while((Get-Date) -lt $deadline){
 $fusion=Get-Process Fusion360 -ErrorAction SilentlyContinue | Select-Object -First 1
 if($fusion){
  $pidCondition=New-Object Windows.Automation.PropertyCondition ([Windows.Automation.AutomationElement]::ProcessIdProperty),([int]$fusion.Id)
  $nameCondition=New-Object Windows.Automation.PropertyCondition ([Windows.Automation.AutomationElement]::NameProperty),'Sign In'
  $condition=New-Object Windows.Automation.AndCondition $pidCondition,$nameCondition
  $button=[Windows.Automation.AutomationElement]::RootElement.FindFirst([Windows.Automation.TreeScope]::Descendants,$condition)
  if($button -and !$button.Current.IsOffscreen -and $button.Current.IsEnabled){
   $invoke=$button.GetCurrentPattern([Windows.Automation.InvokePattern]::Pattern)
   $invoke.Invoke()
   'Native sign-in invoked' | Set-Content (Join-Path $env:LOCALAPPDATA 'FusionWorkstation\Auth\signin-start.txt')
   exit 0
  }
 }
 Start-Sleep -Seconds 2
}
'Fusion sign-in control did not become available' | Set-Content (Join-Path $env:LOCALAPPDATA 'FusionWorkstation\Auth\signin-start.txt')
exit 1
