# Convenience script to start the FastAPI backend
$ErrorActionPreference = "Stop"
Write-Host "Starting RoxStar AI Voice Room Backend..." -ForegroundColor Cyan

$env:PYTHONPATH = (Get-Location).Path
python -m uvicorn backend.app.main:app --reload --port 8000
