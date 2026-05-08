Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$frontendRoot = Join-Path (Split-Path -Parent $PSScriptRoot) 'frontend'
Set-Location $frontendRoot

npm run dev
