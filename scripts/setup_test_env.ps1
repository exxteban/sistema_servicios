param(
    [string]$PythonCommand = "py -3.13"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $root ".venv"
$pythonExe = Join-Path $venvPath "Scripts\python.exe"
$expectedMajorMinor = "3.13"

function Test-VenvHealthy {
    if (!(Test-Path $pythonExe)) {
        return $false
    }

    try {
        & $pythonExe --version | Out-Null
        return $true
    } catch {
        return $false
    }
}

if (!(Test-VenvHealthy)) {
    if (Test-Path $venvPath) {
        Remove-Item -LiteralPath $venvPath -Recurse -Force
    }

    Write-Host "Creando entorno virtual con $PythonCommand"
    Invoke-Expression "$PythonCommand -m venv `"$venvPath`""
}

if (Test-VenvHealthy) {
    $currentMajorMinor = & $pythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    if ($currentMajorMinor -ne $expectedMajorMinor) {
        Write-Host "Recreando .venv para migrar de Python $currentMajorMinor a $expectedMajorMinor"
        Remove-Item -LiteralPath $venvPath -Recurse -Force
        Invoke-Expression "$PythonCommand -m venv `"$venvPath`""
    }
}

Write-Host "Actualizando pip"
& $pythonExe -m pip install --upgrade pip

Write-Host "Instalando dependencias Python de app y testing"
& $pythonExe -m pip install -r (Join-Path $root "requirements-dev.txt")

Write-Host "Instalando dependencias Node del proyecto"
& npm install --prefix $root

Write-Host "Instalando dependencias Node de tienda_online"
& npm install --prefix (Join-Path $root "tienda_online")

Write-Host "Entorno Python listo en $venvPath"
