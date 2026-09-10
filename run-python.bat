@echo off
cd /d "%~dp0python"
if not exist .venv\Scripts\python.exe py -3 -m venv .venv
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m morning_bloom %*
if errorlevel 1 goto fail
exit /b 0
:fail
pause
exit /b 1
