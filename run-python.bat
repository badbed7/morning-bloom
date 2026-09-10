@echo off
setlocal
cd /d "%~dp0python"
if errorlevel 1 goto fail
rem Use a separate environment so an old Python 3.14 venv is never reused.
set "BLOOM_PY=.venv-py312\Scripts\python.exe"
if exist "%BLOOM_PY%" goto validate
py -3.12 -c "import sys,struct; sys.exit(0 if sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if errorlevel 1 goto missing_python
py -3.12 -m venv .venv-py312
if errorlevel 1 goto fail
:validate
"%BLOOM_PY%" -c "import sys,struct; sys.exit(0 if sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if errorlevel 1 goto invalid_venv
"%BLOOM_PY%" -m pip install -r requirements.txt
if errorlevel 1 goto fail
"%BLOOM_PY%" -m morning_bloom %*
if errorlevel 1 goto fail
exit /b 0
:missing_python
echo Python 3.12 64-bit with Python Launcher is required.
echo Install it, then run this file again. Your other Python versions can stay.
echo Check installed versions with: py -0p
goto fail
:invalid_venv
echo The python\.venv-py312 environment is invalid.
echo Rename that environment folder, then run this file again.
echo Game saves are stored separately in LocalAppData.
:fail
pause
exit /b 1
