$ErrorActionPreference = "Stop"

Write-Host "Installing/updating PyInstaller..." -ForegroundColor Cyan
python -m pip install pyinstaller
if ($LASTEXITCODE -ne 0) { throw "PyInstaller install failed" }

Write-Host "Building TikTokLiveBackend.exe..." -ForegroundColor Cyan
python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onedir `
    --name TikTokLiveBackend `
    --collect-all TikTokLive `
    --collect-all obsws_python `
    .\tiktok_backend.py
if ($LASTEXITCODE -ne 0) { throw "TikTokLiveBackend build failed" }

Write-Host "Building single-file TikTokLiveStudio.exe (React + Electron + embedded backend)..." -ForegroundColor Cyan
Push-Location ".\electron_output"
try {
    $dependenciesReady = (
        (Test-Path ".\node_modules\.bin\vite.cmd") -and
        (Test-Path ".\node_modules\.bin\electron-builder.cmd") -and
        (Test-Path ".\node_modules\electron\dist\electron.exe")
    )
    if (-not $dependenciesReady) {
        if (Test-Path ".\package-lock.json") { npm ci } else { npm install }
        if ($LASTEXITCODE -ne 0) { throw "npm dependency install failed" }
    }
    $env:CSC_IDENTITY_AUTO_DISCOVERY = "false"
    npm run test
    if ($LASTEXITCODE -ne 0) { throw "Electron tests failed" }
    npm run dist
    if ($LASTEXITCODE -ne 0) { throw "React/Electron build failed" }
} finally {
    Pop-Location
}

$dataArgs = @()
if (Test-Path ".\videos") {
    $dataArgs = @("--add-data", "videos;videos")
}

New-Item -ItemType Directory -Force -Path ".\dist\videos" | Out-Null
$finalExecutable = ".\dist\TikTokLiveStudio.exe"
try {
    Copy-Item ".\electron_output\dist\TikTokLiveStudio.exe" $finalExecutable -Force
} catch [System.IO.IOException] {
    $finalExecutable = ".\dist\TikTokLiveStudio-new.exe"
    Copy-Item ".\electron_output\dist\TikTokLiveStudio.exe" $finalExecutable -Force
    Write-Host "Existing executable is open; wrote the new build to $finalExecutable" -ForegroundColor Yellow
}
Remove-Item ".\dist\TikTokLiveOutput.exe" -Force -ErrorAction SilentlyContinue
Remove-Item ".\dist\TikTokLiveBackend" -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "Copying videos folder..." -ForegroundColor Cyan
if (Test-Path ".\videos") {
    Copy-Item ".\videos\*" ".\dist\videos" -Recurse -Force
} else {
    Write-Host "No videos folder found. Create dist\videos and copy your MP4 files there." -ForegroundColor Yellow
}
foreach ($configFile in @("gift_config.json", "obs_config.json")) {
    if (Test-Path ".\$configFile") {
        Copy-Item ".\$configFile" ".\dist\$configFile" -Force
    }
}

Write-Host "Done: $((Resolve-Path $finalExecutable).Path)" -ForegroundColor Green
