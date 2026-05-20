param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs,
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $root ".venv\Scripts\python.exe"

if (!(Test-Path $pythonExe)) {
    throw "No existe .venv. Ejecuta primero .\scripts\setup_test_env.ps1"
}

Push-Location $root
try {
    Write-Host "Ejecutando pytest"
    if ($null -eq $PytestArgs -or $PytestArgs.Count -eq 0) {
        & $pythonExe -m pytest
    } else {
        & $pythonExe -m pytest $PytestArgs
    }

    if (-not $SkipFrontend) {
        Write-Host "Validando build frontend de tienda_online"
        & npm --prefix (Join-Path $root "tienda_online") run build
    }
} finally {
    Pop-Location
}
