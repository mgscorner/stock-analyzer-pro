@echo off
setlocal
call "%~dp0deploy_config.bat" || exit /b 1

for /f "usebackq delims=" %%i in ("%PROJECT_ROOT%\deployment\artifacts\latest_release.txt") do set RELEASE_ZIP=%%i

if not exist "%RELEASE_ZIP%" (
  echo Release zip not found: %RELEASE_ZIP%
  exit /b 1
)

scp -i "%SSH_KEY%" "%RELEASE_ZIP%" "%PROJECT_ROOT%\deployment\scripts\bootstrap_vm.sh" "%PROJECT_ROOT%\deployment\scripts\deploy_release.sh" "%DEPLOY_USER%@%DEPLOY_HOST%:%REMOTE_RELEASE_UPLOAD_DIR%/"
if errorlevel 1 exit /b 1

echo Upload complete.
