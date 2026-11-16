param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run scripts\Setup.ps1 first.' }
$env:PYTHONPATH = Join-Path $projectRoot 'backend'
$env:PYTHONUTF8 = '1'
& $pythonPath -m toolguard.cli serve --port $Port
