@echo off
rem Start Wallpaper Editor without a console window (run setup.bat first).
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" "%~dp0run_app.pyw"
