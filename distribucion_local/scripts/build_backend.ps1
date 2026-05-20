[CmdletBinding()]
param(
    [string]$PythonExe = "python",
    [string]$OutputDir = "",
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$distributionRoot = Split-Path -Parent $scriptsDir
$repoRoot = Split-Path -Parent $distributionRoot
$buildRoot = Join-Path $distributionRoot ".build"
$venvPath = Join-Path $buildRoot "venv_backend"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$venvPyInstaller = Join-Path $venvPath "Scripts\pyinstaller.exe"
$backendOutputDir = if ([string]::IsNullOrWhiteSpace($OutputDir)) { Join-Path $distributionRoot "artifacts\backend" } else { $OutputDir }

if ($Clean -and (Test-Path $buildRoot)) {
    Remove-Item -Recurse -Force $buildRoot
}

if (Test-Path $backendOutputDir) {
    Remove-Item -Recurse -Force $backendOutputDir
}
New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null
New-Item -ItemType Directory -Force -Path $backendOutputDir | Out-Null

if (-not (Test-Path $venvPython)) {
    & $PythonExe -m venv $venvPath
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo crear el entorno virtual para build_backend."
    }
}

Push-Location $repoRoot
try {
    & $venvPython -m pip install -r "requirements.txt" pyinstaller
    if ($LASTEXITCODE -ne 0) {
        throw "Falló instalación de dependencias para build_backend."
    }

    $distDir = Join-Path $buildRoot "pyinstaller_dist"
    $workDir = Join-Path $buildRoot "pyinstaller_work"
    $specDir = Join-Path $buildRoot "pyinstaller_spec"
    if (Test-Path $distDir) { Remove-Item -Recurse -Force $distDir }
    if (Test-Path $workDir) { Remove-Item -Recurse -Force $workDir }
    if (Test-Path $specDir) { Remove-Item -Recurse -Force $specDir }

    $appDataSource = Join-Path $repoRoot "app"
    & $venvPyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --name "backend_service" `
        --distpath $distDir `
        --workpath $workDir `
        --specpath $specDir `
        --paths $repoRoot `
        --add-data "$appDataSource;app" `
        --hidden-import "waitress" `
        "run.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Falló el empaquetado de backend con PyInstaller."
    }

    $compiledExe = Join-Path $distDir "backend_service.exe"
    if (-not (Test-Path $compiledExe)) {
        throw "No se encontró backend_service.exe luego del build."
    }

    Copy-Item -Force $compiledExe (Join-Path $backendOutputDir "backend_service.exe")
    Copy-Item -Force ".env.example" (Join-Path $backendOutputDir ".env.example")
}
finally {
    Pop-Location
}

Write-Host "Backend compilado en: $backendOutputDir" -ForegroundColor Green
