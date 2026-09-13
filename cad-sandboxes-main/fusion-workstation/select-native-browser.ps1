$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
Start-Process 'ms-settings:defaultapps?registeredAppMachine=Microsoft%20Edge'
Start-Sleep -Seconds 2
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$deadline=(Get-Date).AddSeconds(30)
while((Get-Date) -lt $deadline){
 $settings=Get-Process SystemSettings -ErrorAction SilentlyContinue | Select-Object -First 1
 if($settings){
  $pidCondition=New-Object Windows.Automation.PropertyCondition ([Windows.Automation.AutomationElement]::ProcessIdProperty),([int]$settings.Id)
  $nameCondition=New-Object Windows.Automation.PropertyCondition ([Windows.Automation.AutomationElement]::NameProperty),'Make Microsoft Edge your default browser'
  $typeCondition=New-Object Windows.Automation.PropertyCondition ([Windows.Automation.AutomationElement]::ControlTypeProperty),([Windows.Automation.ControlType]::Button)
  $condition=New-Object Windows.Automation.AndCondition ([Windows.Automation.Condition[]]@($pidCondition,$nameCondition,$typeCondition))
  $button=[Windows.Automation.AutomationElement]::RootElement.FindFirst([Windows.Automation.TreeScope]::Descendants,$condition)
  if($button){
   $button.GetCurrentPattern([Windows.Automation.InvokePattern]::Pattern).Invoke()
   Start-Sleep -Seconds 2
   $choice=(Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice').ProgId
   $choice | Set-Content (Join-Path $env:LOCALAPPDATA 'FusionWorkstation\Auth\browser-selected.txt')
   if($choice -ne 'MSEdgeHTM'){throw 'Native Edge association was not applied'}
   exit 0
  }
 }
 Start-Sleep -Seconds 1
}
throw 'Windows default-browser control did not become available'
