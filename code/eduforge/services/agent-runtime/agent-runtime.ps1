param(
  [ValidateSet('doctor','web','sdk','verify','package')][string]$Action = 'doctor',
  [string]$Data,
  [string]$Workspace,
  [int]$Port = 3082,
  [string]$Out,
  [switch]$Live
)
$ErrorActionPreference = 'Stop'
$runtimeNode = Join-Path $PSScriptRoot 'runtime/node.exe'
if (-not (Test-Path -LiteralPath $runtimeNode)) { $runtimeNode = (Get-Command node -ErrorAction Stop).Source }
$runtimeArgs = @((Join-Path $PSScriptRoot 'src/cli.mjs'), $Action, '--port', "$Port")
if ($Data) { $runtimeArgs += @('--data', $Data) }
if ($Workspace) { $runtimeArgs += @('--workspace', $Workspace) }
if ($Out) { $runtimeArgs += @('--out', $Out) }
if ($Live) { $runtimeArgs += '--live' }
& $runtimeNode @runtimeArgs
exit $LASTEXITCODE
