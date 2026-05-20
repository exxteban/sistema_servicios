[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$cpu = (Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty ProcessorId)
$board = (Get-CimInstance Win32_BaseBoard | Select-Object -First 1 -ExpandProperty SerialNumber)
$bios = (Get-CimInstance Win32_BIOS | Select-Object -First 1 -ExpandProperty SerialNumber)
$disk = (Get-CimInstance Win32_DiskDrive | Select-Object -First 1 -ExpandProperty SerialNumber)
$raw = "$cpu|$board|$bios|$disk".ToLowerInvariant()
$sha = [System.Security.Cryptography.SHA256]::Create()
$hash = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($raw))
$hex = -join ($hash | ForEach-Object { $_.ToString("x2") })
Write-Output $hex
