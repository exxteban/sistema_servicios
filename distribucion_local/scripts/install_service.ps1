[CmdletBinding()]
param(
    [string]$ServiceName = "SistemaSilvioCelBackend",
    [string]$InstallDir = "C:\Program Files\SistemaSilvioCel",
    [string]$BackendExeRelativePath = "backend\backend_service.exe",
    [string]$Host = "0.0.0.0",
    [int]$Port = 5003,
    [string]$AppConfig = "production",
    [bool]$AllowLocalNetwork = $true
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$serviceExe = Join-Path $InstallDir $BackendExeRelativePath
if (-not (Test-Path $serviceExe)) {
    throw "No se encontró el ejecutable del backend: $serviceExe"
}

$env:HOST = $Host
$env:PORT = "$Port"
$env:APP_CONFIG = $AppConfig
$env:SERVER = "waitress"

$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    if ($existing.Status -ne "Stopped") {
        Stop-Service -Name $ServiceName -Force
    }
    sc.exe delete $ServiceName | Out-Null
    Start-Sleep -Seconds 2
}

$binPath = "`"$serviceExe`""
sc.exe create $ServiceName binPath= $binPath start= auto DisplayName= $ServiceName | Out-Null
sc.exe description $ServiceName "Backend local de Sistema Silvio Cel" | Out-Null
sc.exe failure $ServiceName reset= 86400 actions= restart/60000/restart/60000/restart/60000 | Out-Null

if ($AllowLocalNetwork) {
    Write-Host "Configurando Firewall de Windows para permitir trafico de red local en el puerto $Port..."
    Remove-NetFirewallRule -DisplayName "Sistema Silvio Cel Backend ($ServiceName)" -ErrorAction SilentlyContinue
    New-NetFirewallRule -DisplayName "Sistema Silvio Cel Backend ($ServiceName)" -Direction Inbound -LocalPort $Port -Protocol TCP -Action Allow -Profile Any | Out-Null
}

Start-Service -Name $ServiceName
Get-Service -Name $ServiceName
