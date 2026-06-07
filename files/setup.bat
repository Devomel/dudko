@echo off
REM Налаштування віртуального середовища для price_scraper (Windows)
setlocal

cd /d "%~dp0"

echo Створюю venv у .\venv
python -m venv venv
if errorlevel 1 (
    echo ПОМИЛКА: не вдалося створити venv. Перевір, що Python встановлено і в PATH.
    pause
    exit /b 1
)

echo Активую venv і ставлю залежності
call venv\Scripts\activate.bat

python -m pip install --upgrade pip
pip install -r requirements.txt

echo Встановлюю Chromium для Playwright (це може зайняти кілька хвилин)
playwright install chromium

echo.
echo ════════════════════════════════════════════════════════════════════
echo   ✓ Все готово!
echo.
echo   Активуй venv:    venv\Scripts\activate
echo   Запусти скрапер: python scraper.py 1K0407151BC
echo   З вікном:        python scraper.py 1K0407151BC --headed
echo ════════════════════════════════════════════════════════════════════
echo.
pause
