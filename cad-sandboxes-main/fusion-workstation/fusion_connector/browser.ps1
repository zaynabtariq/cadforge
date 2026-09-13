$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
# The expression travels on encrypted SSH stdin, never in a process argument.
$request=[Console]::In.ReadToEnd() | ConvertFrom-Json
$tabs=Invoke-RestMethod 'http://127.0.0.1:9222/json/list' -TimeoutSec 3
$tab=$tabs | Where-Object { $_.type -eq 'page' -and ([Uri]$_.url).Scheme -eq 'https' -and ([Uri]$_.url).Host -in 'signin.autodesk.com','accounts.autodesk.com' } | Select-Object -First 1
if(!$tab){throw 'No Autodesk sign-in page'}
$endpoint=[Uri]$tab.webSocketDebuggerUrl
if($endpoint.Scheme -ne 'ws' -or $endpoint.Host -notin '127.0.0.1','localhost' -or $endpoint.Port -ne 9222){throw 'Invalid browser endpoint'}
$ws=New-Object Net.WebSockets.ClientWebSocket
$cancel=New-Object Threading.CancellationTokenSource
$cancel.CancelAfter(15000)
try {
 $ws.ConnectAsync($endpoint,$cancel.Token).GetAwaiter().GetResult() | Out-Null
 $message=@{id=1;method='Runtime.evaluate';params=@{expression=$request.expression;returnByValue=$true;awaitPromise=$true;userGesture=$true}} | ConvertTo-Json -Depth 10 -Compress
 $bytes=[Text.Encoding]::UTF8.GetBytes($message)
 $segment=New-Object 'ArraySegment[byte]' -ArgumentList (,$bytes)
 $ws.SendAsync($segment,[Net.WebSockets.WebSocketMessageType]::Text,$true,$cancel.Token).GetAwaiter().GetResult() | Out-Null
 [Array]::Clear($bytes,0,$bytes.Length);$message=$null;$request=$null
 do {
  $stream=New-Object IO.MemoryStream
  do {
   $buffer=New-Object byte[] 16384
   $part=New-Object 'ArraySegment[byte]' -ArgumentList (,$buffer)
   $received=$ws.ReceiveAsync($part,$cancel.Token).GetAwaiter().GetResult()
   $stream.Write($buffer,0,$received.Count)
   if($stream.Length -gt 131072){throw 'Browser response exceeds limit'}
  } while(!$received.EndOfMessage)
  $reply=[Text.Encoding]::UTF8.GetString($stream.ToArray()) | ConvertFrom-Json
  $stream.Dispose()
 } while($reply.id -ne 1)
 if($reply.error -or $reply.result.exceptionDetails){throw 'Browser operation failed'}
 $reply.result.result.value | ConvertTo-Json -Depth 10 -Compress
} finally {$ws.Dispose();$cancel.Dispose()}
