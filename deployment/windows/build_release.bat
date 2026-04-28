@echo off
setlocal
call "%~dp0deploy_config.bat" || exit /b 1

powershell -ExecutionPolicy Bypass -File "%PROJECT_ROOT%\deployment\scripts\package_release.ps1" ^
  -ProjectRoot "%PROJECT_ROOT%" ^
  -FrontendSupabaseUrl "%FRONTEND_SUPABASE_URL%" ^
  -FrontendSupabaseAnonKey "%FRONTEND_SUPABASE_ANON_KEY%" ^
  -FrontendWorkerApiUrl "%FRONTEND_WORKER_API_URL%"

if errorlevel 1 exit /b 1
echo Build complete.
