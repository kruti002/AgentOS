# AgentOS one-command dev launcher (Windows / PowerShell).
# Installs Python deps, builds the web UI, and starts the server.
#
# Usage:  .\scripts\dev.ps1  [-Port 8000] [-SkipWebBuild]

param(
    [int]$Port = 8000,
    [switch]$SkipWebBuild
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "==> Installing Python dependencies..." -ForegroundColor Cyan
python -m pip install -e $root

if (-not $SkipWebBuild) {
    Write-Host "==> Building web UI..." -ForegroundColor Cyan
    Push-Location (Join-Path $root "web")
    npm install
    npm run build
    Pop-Location
}

Write-Host "==> Starting AgentOS on http://127.0.0.1:$Port ..." -ForegroundColor Green
python -m uvicorn server.main:app --host 127.0.0.1 --port $Port
