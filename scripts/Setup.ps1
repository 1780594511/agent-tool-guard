param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
& $Python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required. Supply -Python with the full python.exe path.' }
& '.\.venv\Scripts\python.exe' -m pip install pip==26.3
if ($LASTEXITCODE -ne 0) { throw 'pip bootstrap failed.' }
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.lock
if ($LASTEXITCODE -ne 0) { throw 'Python dependency install failed.' }
& '.\.venv\Scripts\python.exe' -m pip install --no-deps --no-build-isolation -e .
if ($LASTEXITCODE -ne 0) { throw 'Editable project install failed.' }
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
Push-Location -LiteralPath 'frontend'
try { npm.cmd ci; if ($LASTEXITCODE -ne 0) { throw 'npm ci failed.' } }
finally { Pop-Location }
$env:PYTHONPATH = Join-Path $projectRoot 'backend'
& '.\.venv\Scripts\python.exe' -m toolguard.cli init
