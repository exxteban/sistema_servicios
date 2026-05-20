param(
    [switch]$ForceRecreateVenv,
    [switch]$SkipSmokeTest
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $root ".venv"
$pythonExe = Join-Path $venvPath "Scripts\python.exe"
$setupScript = Join-Path $PSScriptRoot "setup_test_env.ps1"

function Invoke-Step {
    param(
        [string]$Label,
        [scriptblock]$Action
    )

    Write-Host $Label
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo '$Label' (exit code $LASTEXITCODE)."
    }
}

if (!(Test-Path $setupScript)) {
    throw "No se encontro el script base: $setupScript"
}

if ($ForceRecreateVenv -and (Test-Path $venvPath)) {
    Write-Host "Eliminando entorno virtual actual (.venv) por -ForceRecreateVenv"
    Remove-Item -LiteralPath $venvPath -Recurse -Force
}

Push-Location $root
try {
    Invoke-Step "Preparando entorno con Python 3.13..." {
        & $setupScript -PythonCommand "py -3.13"
    }

    if (!(Test-Path $pythonExe)) {
        throw "No se pudo crear .venv correctamente."
    }

    Invoke-Step "Verificando versiones clave de runtime..." {
        & $pythonExe -c "import sys, sqlalchemy; import importlib.metadata as m; print('Python=' + sys.version.split()[0] + ' Flask=' + m.version('flask') + ' SQLAlchemy=' + sqlalchemy.__version__)"
    }

    if (-not $SkipSmokeTest) {
        Invoke-Step "Ejecutando smoke test de inicializacion Flask..." {
            & $pythonExe -c "from app import create_app; app = create_app(); print('Smoke test OK: create_app() inicializa correctamente')"
        }
    }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "Migracion a Python 3.13 completada."
Write-Host "Para iniciar la app:"
Write-Host "  .\.venv\Scripts\python.exe run.py"
