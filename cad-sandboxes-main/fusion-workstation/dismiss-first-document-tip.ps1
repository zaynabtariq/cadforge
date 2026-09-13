# One-time dismissal of the observed Fusion Personal information dialog.
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class BridgeSetupMouse {
 [DllImport("user32.dll")] public static extern bool SetCursorPos(int x,int y);
 [DllImport("user32.dll")] public static extern void mouse_event(uint flags,uint x,uint y,uint data,UIntPtr extra);
}
'@
[BridgeSetupMouse]::SetCursorPos(735,434) | Out-Null
[BridgeSetupMouse]::mouse_event(2,0,0,0,[UIntPtr]::Zero)
[BridgeSetupMouse]::mouse_event(4,0,0,0,[UIntPtr]::Zero)
