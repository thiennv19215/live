$ErrorActionPreference = "Stop"

Write-Host "Installing/updating PyInstaller..." -ForegroundColor Cyan
python -m pip install pyinstaller

$dataArgs = @()
if (Test-Path ".\videos") {
    $dataArgs = @("--add-data", "videos;videos")
}

Write-Host "Building TikTokObsControl.exe..." -ForegroundColor Cyan
python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onefile `
    --name TikTokObsControl `
    --collect-all TikTokLive `
    --collect-all obsws_python `
    @dataArgs `
    .\tiktok_obs_gui.py

New-Item -ItemType Directory -Force -Path ".\dist\videos" | Out-Null
Write-Host "Copying videos folder..." -ForegroundColor Cyan
if (Test-Path ".\videos") {
    Copy-Item ".\videos\*" ".\dist\videos" -Recurse -Force
} else {
    Write-Host "No videos folder found. Create dist\videos and copy your MP4 files there." -ForegroundColor Yellow
}

Write-Host "Done: $((Resolve-Path '.\dist\TikTokObsControl.exe').Path)" -ForegroundColor Green
