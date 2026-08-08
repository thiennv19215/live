$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$buildEnvironment = Join-Path $PSScriptRoot ".build-python"
$buildPython = Join-Path $buildEnvironment "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $buildPython)) {
    Write-Host "Creating isolated Python build environment..." -ForegroundColor Cyan
    python -m venv $buildEnvironment
    if ($LASTEXITCODE -ne 0) { throw "Python build environment creation failed" }
}

Write-Host "Installing locked backend/build dependencies..." -ForegroundColor Cyan
& $buildPython -m pip install --disable-pip-version-check -r (Join-Path $PSScriptRoot "requirements-build.txt")
if ($LASTEXITCODE -ne 0) { throw "Backend/build dependency install failed" }

Write-Host "Building TikTokLiveBackend.exe..." -ForegroundColor Cyan
& $buildPython -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onedir `
    --name TikTokLiveBackend `
    --collect-all TikTokLive `
    --collect-all obsws_python `
    --collect-all websockets `
    .\tiktok_backend.py
if ($LASTEXITCODE -ne 0) { throw "TikTokLiveBackend build failed" }

Write-Host "Building TikTokLiveStudio Windows installer (React + Electron + embedded backend)..." -ForegroundColor Cyan
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

$builtInstaller = ".\electron_output\dist\TikTokLiveStudio_Setup_v1.2.0.exe"
if (-not (Test-Path -LiteralPath $builtInstaller)) {
    throw "Installer artifact not found: $builtInstaller"
}

$versionedInstaller = ".\dist\TikTokLiveStudio_Setup_v1.2.0.exe"
$finalInstaller = ".\dist\TikTokLiveStudio_Setup.exe"
Copy-Item -LiteralPath $builtInstaller -Destination $versionedInstaller -Force
Copy-Item -LiteralPath $builtInstaller -Destination $finalInstaller -Force

Remove-Item ".\dist\TikTokLiveStudio.exe" -Force -ErrorAction SilentlyContinue
Remove-Item ".\dist\TikTokLiveStudio_v1.2.0.exe" -Force -ErrorAction SilentlyContinue
Remove-Item ".\dist\TikTokLiveOutput.exe" -Force -ErrorAction SilentlyContinue
Remove-Item ".\dist\TikTokLiveBackend" -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "Done: $((Resolve-Path $finalInstaller).Path)" -ForegroundColor Green
