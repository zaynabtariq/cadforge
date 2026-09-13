# Acknowledge only Fusion's informational Personal document-limit notice.
# This is not a license acceptance or a session-transfer action.
$ErrorActionPreference='Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$deadline=(Get-Date).AddHours(1)
while((Get-Date) -lt $deadline){
 try {
  $windows=[Windows.Automation.AutomationElement]::RootElement.FindAll([Windows.Automation.TreeScope]::Children,[Windows.Automation.Condition]::TrueCondition)
  foreach($w in $windows){
   if($w.Current.Name -notlike '*Autodesk Fusion*'){continue}
   $name=New-Object Windows.Automation.PropertyCondition ([Windows.Automation.AutomationElement]::NameProperty),'About Your Fusion Documents'
   if(!$w.FindFirst([Windows.Automation.TreeScope]::Descendants,$name)){continue}
   $type=New-Object Windows.Automation.PropertyCondition ([Windows.Automation.AutomationElement]::ControlTypeProperty),([Windows.Automation.ControlType]::Button)
   $buttons=$w.FindAll([Windows.Automation.TreeScope]::Descendants,$type)
   foreach($button in $buttons){
    if($button.Current.Name -match '(?i)^ok[.,]?\s*got it[.!]?$' -and !$button.Current.IsOffscreen -and $button.Current.IsEnabled){
     $button.GetCurrentPattern([Windows.Automation.InvokePattern]::Pattern).Invoke()
     exit 0
    }
   }
  }
 } catch {}
 Start-Sleep -Seconds 3
}
