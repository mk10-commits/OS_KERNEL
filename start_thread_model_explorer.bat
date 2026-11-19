@echo off
setlocal
cd /d "%~dp0"
title Thread Model Explorer

where py >nul 2>&1
if not errorlevel 1 (
  start "Thread Model Explorer Server" cmd /k py -3 "%~dp0web_app.py"
  goto :open_browser
)

if exist "%LocalAppData%\Programs\Python\Python310\python.exe" (
  start "Thread Model Explorer Server" "%LocalAppData%\Programs\Python\Python310\python.exe" "%~dp0web_app.py"
  goto :open_browser
)

for /f "delims=" %%P in ('where python 2^>nul') do if not defined PYTHON set "PYTHON=%%P"
if defined PYTHON (
  start "Thread Model Explorer Server" "%PYTHON%" "%~dp0web_app.py"
  goto :open_browser
)

echo Python 3.10 or newer was not found. Install Python and run this file again.
pause
goto :end

:open_browser
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8000/"
:end
endlocal
