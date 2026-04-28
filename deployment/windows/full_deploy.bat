@echo off
setlocal
call "%~dp0deploy_config.bat" || exit /b 1

if exist "%PROJECT_ROOT%\deployment\windows\worker.env" (
  call "%~dp0upload_worker_env.bat" || exit /b 1
)

call "%~dp0build_release.bat" || exit /b 1
call "%~dp0upload_release.bat" || exit /b 1
call "%~dp0deploy_remote.bat" || exit /b 1
call "%~dp0smoke_test.bat" || exit /b 1
echo Full deploy complete.
