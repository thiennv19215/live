$ErrorActionPreference = "Stop"

Write-Host "Building TikTokLiveStudio.exe (React + Electron)..." -ForegroundColor Cyan
Push-Location ".\electron_output"
try {
    if (Test-Path ".\package-lock.json") {
        npm ci
    } else {
        npm install
    }
    if ($LASTEXITCODE -ne 0) { throw "npm dependency install failed" }
    $env:CSC_IDENTITY_AUTO_DISCOVERY = "false"
    npm run test
    if ($LASTEXITCODE -ne 0) { throw "Electron tests failed" }
    npm run dist
    if ($LASTEXITCODE -ne 0) { throw "React/Electron build failed" }
} finally {
    Pop-Location
}

Write-Host "Installing/updating PyInstaller..." -ForegroundColor Cyan
python -m pip install pyinstaller
if ($LASTEXITCODE -ne 0) { throw "PyInstaller install failed" }

Write-Host "Building TikTokLiveBackend.exe..." -ForegroundColor Cyan
python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onefile `
    --name TikTokLiveBackend `
    --collect-all TikTokLive `
    --collect-all obsws_python `
    .\tiktok_backend.py
if ($LASTEXITCODE -ne 0) { throw "TikTokLiveBackend build failed" }

$dataArgs = @()
if (Test-Path ".\videos") {
    $dataArgs = @("--add-data", "videos;videos")
}

New-Item -ItemType Directory -Force -Path ".\dist\videos" | Out-Null
Copy-Item ".\electron_output\dist\TikTokLiveStudio.exe" ".\dist\TikTokLiveStudio.exe" -Force
Copy-Item ".\electron_output\dist\TikTokLiveStudio.exe" ".\dist\TikTokLiveOutput.exe" -Force
Write-Host "Copying videos folder..." -ForegroundColor Cyan
if (Test-Path ".\videos") {
    Copy-Item ".\videos\*" ".\dist\videos" -Recurse -Force
} else {
    Write-Host "No videos folder found. Create dist\videos and copy your MP4 files there." -ForegroundColor Yellow
}

Write-Host "Done: $((Resolve-Path '.\dist\TikTokLiveBackend.exe').Path)" -ForegroundColor Green
Write-Host "Done: $((Resolve-Path '.\dist\TikTokLiveStudio.exe').Path)" -ForegroundColor Green
Write-Host "Done: $((Resolve-Path '.\dist\TikTokLiveOutput.exe').Path)" -ForegroundColor Green
