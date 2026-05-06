$ErrorActionPreference = "Stop"

$AppName = "BareBone VPN"
$RootDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

Set-Location $RootDir

Write-Host "=== BareBoneVPN Windows release build ==="
Write-Host "Root: $RootDir"
Write-Host ""

if (-not (Get-Command go -ErrorAction SilentlyContinue)) {
    Write-Host "[X] Go is not installed"
    exit 1
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "[X] Python is not installed"
    exit 1
}

Write-Host "[*] Cleaning old build..."

if (Test-Path "build") {
    Remove-Item -Recurse -Force "build"
}

if (Test-Path "dist") {
    Remove-Item -Recurse -Force "dist"
}

if (Test-Path "app\BareBoneVPN.exe") {
    Remove-Item -Force "app\BareBoneVPN.exe"
}

if (Test-Path "$AppName.spec") {
    Remove-Item -Force "$AppName.spec"
}

Get-ChildItem -Path . -Recurse -Force -Filter "__pycache__" -Directory | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path . -Recurse -Force -Filter "*.pyc" | Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host "[*] Preparing Python venv..."

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

& ".\.venv\Scripts\Activate.ps1"

python -m pip install --upgrade pip
pip install -r app\requirements.txt pyinstaller

Write-Host "[*] Building BareBoneVPN binary..."

go build -o app\BareBoneVPN.exe cmd\barebone\main.go

if (-not (Test-Path "app\BareBoneVPN.exe")) {
    Write-Host "[X] app\BareBoneVPN.exe was not created"
    exit 1
}

Write-Host "[*] Building Windows app..."

pyinstaller `
    --clean `
    --windowed `
    --name "$AppName" `
    --add-binary "app\BareBoneVPN.exe;." `
    --icon assets/icon.ico `
    --paths app `
    app\app_windows.py

$AppDir = "dist\$AppName"
$AppExe = "$AppDir\$AppName.exe"

if (-not (Test-Path $AppExe)) {
    Write-Host "[X] App was not created: $AppExe"
    exit 1
}

Write-Host "[*] Creating zip..."

$ZipPath = "dist\$AppName Windows.zip"

if (Test-Path $ZipPath) {
    Remove-Item -Force $ZipPath
}

Compress-Archive -Path $AppDir -DestinationPath $ZipPath -Force

Write-Host ""
Write-Host "[+] Done"
Write-Host "App: $AppExe"
Write-Host "Zip: $ZipPath"