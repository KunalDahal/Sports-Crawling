$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $root "backend"
$frontendDir = Join-Path $root "frontend"

function Test-PortInUse {
    param([int]$Port)
    $listeners = @(
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    )
    return $listeners.Count -gt 0
}

function Get-FreePort {
    param([int]$StartPort)
    $port = $StartPort
    while (Test-PortInUse -Port $port) {
        $port++
    }
    return $port
}

if (-not (Test-Path $backendDir)) {
    throw "Backend directory not found: $backendDir"
}
if (-not (Test-Path $frontendDir)) {
    throw "Frontend directory not found: $frontendDir"
}

$backendPort = Get-FreePort -StartPort 8080
$frontendPort = Get-FreePort -StartPort 5173
$apiBase = "http://127.0.0.1:$backendPort"

if ($backendPort -ne 8080) {
    Write-Host "Port 8080 is busy. Starting backend on $backendPort instead."
}
if ($frontendPort -ne 5173) {
    Write-Host "Port 5173 is busy. Starting frontend on $frontendPort instead."
}

Write-Host "Starting backend in a new terminal..."
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "`$env:ADDR=':$backendPort'; Set-Location '$backendDir'; go run .\cmd\server"
)

Start-Sleep -Seconds 1

Write-Host "Starting frontend in a new terminal..."
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "`$env:VITE_API_BASE='$apiBase'; Set-Location '$frontendDir'; npm.cmd run dev -- --host 127.0.0.1 --port $frontendPort --strictPort"
)

Write-Host ""
Write-Host "Project launch started."
Write-Host "Frontend: http://127.0.0.1:$frontendPort"
Write-Host "Backend:  $apiBase"
Write-Host ""
Write-Host "Use Ctrl+C in each terminal to stop."
