@echo off
rem Wallpaper Editor - one-click setup for a new Windows PC.
rem   setup.bat               : create .venv, install packages, run tests, create desktop shortcut
rem   setup.bat --no-shortcut : same, but skip the desktop shortcut
setlocal
cd /d "%~dp0"

set "PY=python"
where py >nul 2>nul && set "PY=py -3"
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>nul
if errorlevel 1 (
    echo [ERROR] Python 3.10 or later is required: https://www.python.org/downloads/
    echo         Check "Add python.exe to PATH" and "tcl/tk" during installation.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PY% -m venv .venv || goto :error
)

echo Installing packages...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements-dev.txt || goto :error

echo Running unit tests...
".venv\Scripts\python.exe" -m pytest tests -q
if errorlevel 1 echo [WARN] Some tests failed. The app may still start.

if /i not "%~1"=="--no-shortcut" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_shortcut.ps1"
)

echo.
echo Setup complete. Start the app with the desktop shortcut or run_app.bat
pause
exit /b 0

:error
echo [ERROR] Setup failed.
pause
exit /b 1
