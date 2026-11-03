# Builds the public utility from the included GPL-3.0 source; no game access.
$ErrorActionPreference = 'Stop'
$taskPackage = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$taskCompiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$taskOutput = Join-Path $taskPackage 'NoMoFOMO + Hidden Content Unlocker Mod.exe'
$taskArguments = @('/nologo', '/optimize+', '/platform:x64', '/target:winexe',
    '/r:System.Windows.Forms.dll', '/r:System.Drawing.dll', '/r:System.Web.Extensions.dll',
    ('/out:' + $taskOutput), ('/win32manifest:' + (Join-Path $PSScriptRoot 'app.manifest')),
    ('/resource:' + (Join-Path $PSScriptRoot 'Profiles.json') + ',Profiles'),
    ('/resource:' + (Join-Path $PSScriptRoot 'Schema.json') + ',Schema'),
    ('/resource:' + (Join-Path $PSScriptRoot 'SwapTargets.json') + ',SwapTargets'))
foreach ($taskName in @('App.cs','ExportCore.cs','StandaloneCore.cs','SemanticEditor.cs','MenuTheme.cs','StratagemSwaps.cs')) {
    $taskArguments += Join-Path $PSScriptRoot $taskName
}
& $taskCompiler @taskArguments
if ($LASTEXITCODE -ne 0) { throw 'Compilation failed.' }
Write-Output "Built $taskOutput"
