[CmdletBinding()]
param(
    [string]$OutputDir = "",
    [switch]$PublishToFlaskStatic = $true
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$distributionRoot = Split-Path -Parent $scriptsDir
$repoRoot = Split-Path -Parent $distributionRoot
$tiendaOnlinePath = Join-Path $repoRoot "tienda_online"
$frontendOutputDir = if ([string]::IsNullOrWhiteSpace($OutputDir)) { Join-Path $distributionRoot "artifacts\frontend" } else { $OutputDir }

if (-not (Test-Path (Join-Path $tiendaOnlinePath "package.json"))) {
    throw "No se encontró tienda_online/package.json."
}

if (Test-Path $frontendOutputDir) {
    Remove-Item -Recurse -Force $frontendOutputDir
}
New-Item -ItemType Directory -Force -Path $frontendOutputDir | Out-Null

Push-Location $tiendaOnlinePath
try {
    npm ci
    if ($LASTEXITCODE -ne 0) {
        throw "Falló npm ci en tienda_online."
    }

    npm run build
    if ($LASTEXITCODE -ne 0) {
        throw "Falló npm run build en tienda_online."
    }
}
finally {
    Pop-Location
}

$defaultDistPath = Join-Path $tiendaOnlinePath "dist"
$flaskStaticDist = Join-Path $repoRoot "app\static\tienda_dist"
$sourceDistPath = if (Test-Path $defaultDistPath) { $defaultDistPath } elseif (Test-Path $flaskStaticDist) { $flaskStaticDist } else { "" }
if ([string]::IsNullOrWhiteSpace($sourceDistPath)) {
    throw "No se encontró salida de build del frontend ni en dist ni en app/static/tienda_dist."
}

Copy-Item -Recurse -Force (Join-Path $sourceDistPath "*") $frontendOutputDir

if ($PublishToFlaskStatic) {
    $sourceDistFullPath = [System.IO.Path]::GetFullPath($sourceDistPath)
    $flaskStaticFullPath = [System.IO.Path]::GetFullPath($flaskStaticDist)
    if ($sourceDistFullPath -ne $flaskStaticFullPath) {
        if (Test-Path $flaskStaticDist) {
            Remove-Item -Recurse -Force $flaskStaticDist
        }
        New-Item -ItemType Directory -Force -Path $flaskStaticDist | Out-Null
        Copy-Item -Recurse -Force (Join-Path $sourceDistPath "*") $flaskStaticDist
    }
}

Write-Host "Frontend compilado en: $frontendOutputDir" -ForegroundColor Green
