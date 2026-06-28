@echo off
setlocal
cd /d "%~dp0"

where cl >nul 2>nul
if %ERRORLEVEL%==0 (
  where rc >nul 2>nul
  if %ERRORLEVEL%==0 (
    rc /nologo /fo cardbox-open.res cardbox-open.rc
    cl /nologo /O2 /DUNICODE /D_UNICODE /Fe:cardbox-open.exe cardbox-open.c cardbox-open.res shell32.lib user32.lib /link /SUBSYSTEM:WINDOWS
  ) else (
    cl /nologo /O2 /DUNICODE /D_UNICODE /Fe:cardbox-open.exe cardbox-open.c shell32.lib user32.lib /link /SUBSYSTEM:WINDOWS
  )
  exit /b %ERRORLEVEL%
)

where gcc >nul 2>nul
if %ERRORLEVEL%==0 (
  where windres >nul 2>nul
  if %ERRORLEVEL%==0 (
    windres cardbox-open.rc cardbox-open-resource.o
    gcc -O2 -municode -mwindows -o cardbox-open.exe cardbox-open.c cardbox-open-resource.o -lshell32 -luser32
  ) else (
    gcc -O2 -municode -mwindows -o cardbox-open.exe cardbox-open.c -lshell32 -luser32
  )
  exit /b %ERRORLEVEL%
)

echo cl or gcc was not found. Install Visual Studio Build Tools or MinGW-w64.
exit /b 1
