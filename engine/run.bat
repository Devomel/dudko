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

if "%~1"=="" (
    echo Usage: run.bat ARTICLE [options]
    echo.
    echo   run.bat 1K0407151BC
    echo   run.bat 1K0407151BC --headed
    echo   run.bat 1K0407151BC --json results.json
    echo   run.bat 1K0407151BC --concurrency 5
    echo   run.bat 1K0407151BC -v
    exit /b 0
)

"%PYTHON%" "%SCRIPT_DIR%scraper.py" %*
