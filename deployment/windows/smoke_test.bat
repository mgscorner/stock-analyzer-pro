@echo off
setlocal
call "%~dp0deploy_config.bat" || exit /b 1

powershell -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$hostName = '%PUBLIC_HOST%';" ^
  "$schemes = @('https','http');" ^
  "$selected = $null;" ^
  "foreach ($scheme in $schemes) {" ^
  "  try {" ^
  "    $root = Invoke-WebRequest -UseBasicParsing -Uri ($scheme + '://' + $hostName + '/');" ^
  "    Write-Host ('Root status (' + $scheme + '): ' + [int]$root.StatusCode);" ^
  "    $selected = $scheme;" ^
  "    break;" ^
  "  } catch {" ^
  "    Write-Host ('Root check failed for ' + $scheme + ': ' + $_.Exception.Message);" ^
  "  }" ^
  "}" ^
  "if (-not $selected) { throw 'Neither HTTPS nor HTTP root endpoint is reachable.' }" ^
  "$api = Invoke-WebRequest -UseBasicParsing -Uri ($selected + '://' + $hostName + '/api/health');" ^
  "Write-Host ('API health status (' + $selected + '): ' + [int]$api.StatusCode);" ^
  "Write-Host $api.Content;" ^
  "Write-Host ('Smoke test succeeded using ' + $selected.ToUpper() + '.');"
if errorlevel 1 exit /b 1

echo Smoke test complete.
