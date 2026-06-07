@echo off
chcp 65001 >nul
setlocal

set "SCRIPT_DIR=%~dp0"
set "PYTHON=%SCRIPT_DIR%venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo ERROR: venv not found. Run setup.bat first.
    pause
    exit /b 1
)

"%PYTHON%" "%SCRIPT_DIR%recommend.py" %*
