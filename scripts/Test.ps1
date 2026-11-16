$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
New-Item -ItemType Directory -Path '.local' -Force | Out-Null
& '.\.venv\Scripts\python.exe' -m pytest --basetemp=.local/pytest
if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed.' }
& '.\.venv\Scripts\ruff.exe' check backend tests scripts
if ($LASTEXITCODE -ne 0) { throw 'Python lint failed.' }
Push-Location -LiteralPath 'frontend'
try { npm.cmd run build; if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' } }
finally { Pop-Location }
