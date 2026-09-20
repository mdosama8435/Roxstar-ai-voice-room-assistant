# Convenience script to run all tests across backend and agents
$ErrorActionPreference = "Stop"
Write-Host "Running RoxStar Python Test Suite..." -ForegroundColor Cyan

$env:PYTHONPATH = (Get-Location).Path
python -m pytest

Write-Host "`nRunning Frontend Type Check..." -ForegroundColor Cyan
Set-Location frontend
npm run type-check
Set-Location ..

Write-Host "`nAll verification checks passed successfully!" -ForegroundColor Green
