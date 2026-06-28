@echo off
setlocal EnableExtensions
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
    python "%~dp0build-cardbox.py"
) else (
    py -3 "%~dp0build-cardbox.py"
)

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed.
) else (
    echo.
    echo [INFO] Build finished.
)

echo.
pause
exit /b %errorlevel%
