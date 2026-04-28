@echo off
setlocal
call "%~dp0deploy_config.bat" || exit /b 1

for /f "usebackq delims=" %%i in ("%PROJECT_ROOT%\deployment\artifacts\latest_release.txt") do set RELEASE_ZIP=%%i
for %%f in ("%RELEASE_ZIP%") do set RELEASE_FILE=%%~nxf

ssh -i "%SSH_KEY%" "%DEPLOY_USER%@%DEPLOY_HOST%" "bash %REMOTE_RELEASE_UPLOAD_DIR%/bootstrap_vm.sh && bash %REMOTE_RELEASE_UPLOAD_DIR%/deploy_release.sh %REMOTE_RELEASE_UPLOAD_DIR%/%RELEASE_FILE% %PUBLIC_HOST% %LETSENCRYPT_EMAIL%"
if errorlevel 1 exit /b 1

echo Remote deploy complete.
