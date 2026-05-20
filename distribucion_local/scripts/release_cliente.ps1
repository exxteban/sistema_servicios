[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ClienteId,
    [Parameter(Mandatory = $true)]
    [string]$ClienteNombre,
    [Parameter(Mandatory = $true)]
    [string]$Version,
    [Parameter(Mandatory = $true)]
    [string]$Expira,
    [Parameter(Mandatory = $true)]
    [string]$MachineFingerprint,
    [string]$Plan = "local-premium",
    [string]$SigningSecret = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$distributionRoot = Split-Path -Parent $scriptsDir
$installerDir = Join-Path $distributionRoot "installer"
$artifactsDir = Join-Path $distributionRoot "artifacts"
$licenseDir = Join-Path $artifactsDir "license"
$licensePath = Join-Path $licenseDir "license.dat"

New-Item -ItemType Directory -Force -Path $licenseDir | Out-Null

& (Join-Path $scriptsDir "build_backend.ps1")
if ($LASTEXITCODE -ne 0) {
    throw "Falló build_backend.ps1"
}

& (Join-Path $scriptsDir "build_frontend.ps1")
if ($LASTEXITCODE -ne 0) {
    throw "Falló build_frontend.ps1"
}

$licenseScript = Join-Path $distributionRoot "licensing\generate_license.py"
$secretToUse = if ([string]::IsNullOrWhiteSpace($SigningSecret)) { $env:LICENSE_SIGNING_SECRET } else { $SigningSecret }
if ([string]::IsNullOrWhiteSpace($secretToUse)) {
    throw "Debes pasar -SigningSecret o definir LICENSE_SIGNING_SECRET."
}

python $licenseScript `
    --cliente-id $ClienteId `
    --cliente-nombre $ClienteNombre `
    --plan $Plan `
    --machine-fingerprint $MachineFingerprint `
    --expira $Expira `
    --features "core,backup,updates" `
    --secret $secretToUse `
    --output $licensePath
if ($LASTEXITCODE -ne 0) {
    throw "Falló generación de license.dat"
}

$isccCandidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
)
$isccPath = $isccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $isccPath) {
    throw "No se encontró ISCC.exe. Instala Inno Setup 6."
}

$issPath = Join-Path $installerDir "Setup.iss"
$outputBaseName = "Setup_{0}_{1}" -f $ClienteId, $Version
& $isccPath `
    "/DAppVersion=$Version" `
    "/DClienteId=$ClienteId" `
    "/DOutputBaseFilename=$outputBaseName" `
    $issPath
if ($LASTEXITCODE -ne 0) {
    throw "Falló compilación de instalador Inno Setup."
}

Write-Host "Release generado para cliente: $ClienteId" -ForegroundColor Green
