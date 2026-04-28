@echo off
setlocal
call "%~dp0deploy_config.bat" || exit /b 1

set LOCAL_WORKER_ENV=%PROJECT_ROOT%\deployment\windows\worker.env

if not exist "%LOCAL_WORKER_ENV%" (
  echo Missing local worker env file: %LOCAL_WORKER_ENV%
  echo Create it first, based on worker\.env.example.
  exit /b 1
)

scp -i "%SSH_KEY%" "%LOCAL_WORKER_ENV%" "%DEPLOY_USER%@%DEPLOY_HOST%:%REMOTE_RELEASE_UPLOAD_DIR%/worker.env"
if errorlevel 1 exit /b 1

ssh -i "%SSH_KEY%" "%DEPLOY_USER%@%DEPLOY_HOST%" "sudo mkdir -p /opt/stock-analyzer/env && sudo mv %REMOTE_RELEASE_UPLOAD_DIR%/worker.env /opt/stock-analyzer/env/worker.env && sudo chown ubuntu:ubuntu /opt/stock-analyzer/env/worker.env && sudo chmod 600 /opt/stock-analyzer/env/worker.env"
if errorlevel 1 exit /b 1

echo Worker env uploaded.
