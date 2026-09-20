# Convenience script to start the Agent Worker process
$ErrorActionPreference = "Stop"
Write-Host "Starting RoxStar AI Agent Worker..." -ForegroundColor Cyan

$env:PYTHONPATH = (Get-Location).Path
python -m agents.app.main
