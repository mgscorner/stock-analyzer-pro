param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$OutputDir = "",
    [switch]$SkipFrontendBuild,
    [string]$FrontendSupabaseUrl = "",
    [string]$FrontendSupabaseAnonKey = "",
    [string]$FrontendWorkerApiUrl = ""
)

$ErrorActionPreference = "Stop"

function Require-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Name"
    }
}

Require-Command powershell
Require-Command npm.cmd

$projectName = Split-Path $ProjectRoot -Leaf
$frontendDir = Join-Path $ProjectRoot "frontend"
$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) "stock_analyzer_release_staging"
$latestReleaseFile = ""

if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = Join-Path $ProjectRoot "deployment\artifacts"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$latestReleaseFile = Join-Path $OutputDir "latest_release.txt"

if (-not $SkipFrontendBuild) {
    Write-Host "Building frontend..."
    Push-Location $frontendDir
    try {
        $generatedEnv = Join-Path $frontendDir ".env.production.local"
        if ($FrontendSupabaseUrl -or $FrontendSupabaseAnonKey -or $FrontendWorkerApiUrl) {
            @(
                "VITE_SUPABASE_URL=$FrontendSupabaseUrl"
                "VITE_SUPABASE_ANON_KEY=$FrontendSupabaseAnonKey"
                "VITE_WORKER_API_URL=$FrontendWorkerApiUrl"
            ) | Set-Content -LiteralPath $generatedEnv -Encoding ascii
        }
        npm.cmd install
        npm.cmd run build
    }
    finally {
        if (Test-Path $generatedEnv) {
            Remove-Item -LiteralPath $generatedEnv -Force
        }
        Pop-Location
    }
}

$distDir = Join-Path $frontendDir "dist"
if (-not (Test-Path $distDir)) {
    throw "Missing frontend build output: $distDir"
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$stagingDir = Join-Path $tempRoot "${projectName}_release_$timestamp"
$zipPath = "$stagingDir.zip"
$finalZipPath = Join-Path $OutputDir "${projectName}_release_$timestamp.zip"

if (Test-Path $stagingDir) {
    Remove-Item -LiteralPath $stagingDir -Recurse -Force
}
if (Test-Path $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
if (Test-Path $finalZipPath) {
    Remove-Item -LiteralPath $finalZipPath -Force
}

Write-Host "Preparing release folder..."
New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
New-Item -ItemType Directory -Force -Path $stagingDir | Out-Null
Copy-Item -LiteralPath $ProjectRoot -Destination (Join-Path $stagingDir $projectName) -Recurse -Force

$copiedRoot = Join-Path $stagingDir $projectName

$pathsToRemove = @(
    (Join-Path $copiedRoot ".git"),
    (Join-Path $copiedRoot "frontend\node_modules"),
    (Join-Path $copiedRoot "worker\__pycache__"),
    (Join-Path $copiedRoot "frontend\src\__pycache__"),
    (Join-Path $copiedRoot "worker\local_test_scripts"),
    (Join-Path $copiedRoot "deployment\artifacts"),
    (Join-Path $copiedRoot "deployment\windows\deploy_config.bat"),
    (Join-Path $copiedRoot "deployment\windows\worker.env")
)

foreach ($path in $pathsToRemove) {
    if (Test-Path $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
    }
}

$deploymentCopyDir = Join-Path $copiedRoot "deployment"
if (Test-Path $deploymentCopyDir) {
    Get-ChildItem -LiteralPath $deploymentCopyDir -File -Filter "*.key*" -ErrorAction SilentlyContinue | Remove-Item -Force
}

Write-Host "Compressing release archive..."
Compress-Archive -Path $stagingDir -DestinationPath $zipPath -Force
Move-Item -LiteralPath $zipPath -Destination $finalZipPath -Force
Set-Content -LiteralPath $latestReleaseFile -Value $finalZipPath -Encoding ascii

$manifest = [ordered]@{
    release_zip = $finalZipPath
    release_name = Split-Path $finalZipPath -Leaf
    built_at_utc = (Get-Date).ToUniversalTime().ToString("o")
}
$manifestPath = Join-Path $OutputDir "latest_release_manifest.json"
$manifest | ConvertTo-Json | Set-Content -LiteralPath $manifestPath -Encoding utf8

Write-Host ""
Write-Host "Release package ready:"
Write-Host "  Folder: $stagingDir"
Write-Host "  Zip:    $finalZipPath"
Write-Host ""
Write-Host "Upload the zip to the Oracle VM, unzip it, then run:"
Write-Host "  bash /opt/stock-analyzer/app/$projectName/deployment/scripts/oracle_bootstrap.sh <your-domain>"
