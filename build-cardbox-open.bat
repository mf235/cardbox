@echo off
setlocal
cd /d "%~dp0"

python build-cardbox.py --launcher-only
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

if not exist cardbox-open.exe (
  echo cardbox-open.exe was not created.
  exit /b 1
)

echo cardbox-open.exe build complete.
exit /b 0
