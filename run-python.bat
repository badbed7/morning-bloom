@echo off
setlocal
rem Python stays installed on the PC; versioned game files live in LocalAppData.
py -3.12 -c "import sys,struct,tkinter; sys.exit(0 if sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if errorlevel 1 goto missing_python
py -3.12 "%~dp0release\launcher.py" --python %*
if errorlevel 1 goto fail
exit /b 0
:missing_python
echo Python 3.12 64-bit with Python Launcher and Tcl/Tk is required.
echo Install it, then run this file again. Your other Python versions can stay.
echo Check installed versions with: py -0p
:fail
pause
exit /b 1
