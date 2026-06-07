@echo off
:: Запуск/зупинка системи AutoParts Monitor (Windows)
::
:: Використання:
::   start.bat           — запуск всього
::   start.bat --stop    — зупинка всього
::   start.bat --logs    — показати логи у реальному часі

setlocal EnableDelayedExpansion

set ROOT=%~dp0
set ROOT=%ROOT:~0,-1%
set VENV=%ROOT%\.venv
set DATA=%ROOT%\data
set LOG_API=%DATA%\api.log
set LOG_FRONT=%DATA%\frontend.log
set PIDS=%DATA%\pids.txt

if not exist "%DATA%" mkdir "%DATA%"

:: ── --stop ─────────────────────────────────────────────────────────────────
if /I "%1"=="--stop" goto :STOP

:: ── --logs ─────────────────────────────────────────────────────────────────
if /I "%1"=="--logs" goto :LOGS

:: ── Запуск ─────────────────────────────────────────────────────────────────
echo.
echo ============================================================
echo    AutoParts Monitor -- zapusk systemy (Windows)
echo ============================================================
echo.

:: 1. Перевірка залежностей
echo [1/6] Perevirka zalezhnostey...

where docker >nul 2>&1 || (echo [ERR] Docker ne vstanovleno & exit /b 1)
docker compose version >nul 2>&1 || (echo [ERR] docker compose ne znajdeno & exit /b 1)
where python >nul 2>&1 || where python3 >nul 2>&1 || (echo [ERR] Python ne vstanovleno & exit /b 1)
where node >nul 2>&1 || (echo [ERR] Node.js ne vstanovleno & exit /b 1)
where npm >nul 2>&1  || (echo [ERR] npm ne znajdeno & exit /b 1)
echo [OK] Usі zalezhnosti znayjdeni

:: 2. Python venv
echo [2/6] Python venv...
if not exist "%VENV%\Scripts\python.exe" (
    echo     Stvorenia venv...
    python -m venv "%VENV%"
)
"%VENV%\Scripts\python.exe" -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo     Vstanovlenia Python zalezhnostey...
    "%VENV%\Scripts\pip.exe" install --quiet --upgrade pip
    "%VENV%\Scripts\pip.exe" install --quiet -r "%ROOT%\files\requirements.txt"
    "%VENV%\Scripts\pip.exe" install --quiet -r "%ROOT%\api\requirements.txt"
    echo [OK] Python zalezhnosti vstanovleni
) else (
    echo [OK] venv hotovyj
)

:: 3. Node.js залежності
echo [3/6] Node.js zalezhnosti...
if not exist "%ROOT%\frontend\node_modules" (
    echo     npm install...
    call npm --prefix "%ROOT%\frontend" install --silent
    echo [OK] node_modules vstanovleni
) else (
    echo [OK] node_modules vzhe ie
)

:: 4. PostgreSQL
echo [4/6] PostgreSQL...
docker compose -f "%ROOT%\docker-compose.yml" up -d db
echo     Ochikuvannia gotovnosti BD...
:WAIT_DB
timeout /t 2 /nobreak >nul
docker compose -f "%ROOT%\docker-compose.yml" exec -T db pg_isready -U scrapper -d scrapper -q >nul 2>&1
if errorlevel 1 goto :WAIT_DB
echo [OK] PostgreSQL hotovyj (localhost:5433)

:: 5. FastAPI
echo [5/6] FastAPI...
> "%LOG_API%" echo.
start /B "%VENV%\Scripts\uvicorn.exe" main:app ^
    --host 0.0.0.0 --port 8000 --reload ^
    --app-dir "%ROOT%\api" >> "%LOG_API%" 2>&1

echo     Ochikuvannia gotovnosti API...
:WAIT_API
timeout /t 2 /nobreak >nul
curl -sf http://localhost:8000/health >nul 2>&1
if errorlevel 1 goto :WAIT_API
echo [OK] FastAPI hotovyj

:: 6. Next.js
echo [6/6] Next.js...
set NEXT_PUBLIC_API_URL=http://localhost:8000
> "%LOG_FRONT%" echo.
start /B cmd /c "set NEXT_PUBLIC_API_URL=http://localhost:8000 && npm --prefix "%ROOT%\frontend" run dev >> "%LOG_FRONT%" 2>&1"

echo     Ochikuvannia hotovnosti frontu...
:WAIT_FRONT
timeout /t 3 /nobreak >nul
curl -sf http://localhost:3000 >nul 2>&1
if errorlevel 1 goto :WAIT_FRONT
echo [OK] Next.js hotovyj

:: Готово
echo.
echo ============================================================
echo   SYSTEMA ZAPUSHCHENA!
echo.
echo   Frontend:  http://localhost:3000
echo   API:       http://localhost:8000
echo   API Docs:  http://localhost:8000/docs
echo   DB:        localhost:5433
echo.
echo   Lohy:  start.bat --logs
echo   Stop:  start.bat --stop
echo ============================================================
echo.
echo Natisni Ctrl+C abo zakrij vikno dlya zupynky...
pause >nul
goto :EOF

:: ── --stop ─────────────────────────────────────────────────────────────────
:STOP
echo Zupynka servісів...
taskkill /F /IM uvicorn.exe /T >nul 2>&1 && echo [OK] API zupyneno    || echo [ ] uvicorn ne zapushchenij
taskkill /F /IM node.exe    /T >nul 2>&1 && echo [OK] Node zupyneno   || echo [ ] node ne zapushchenij
docker compose -f "%ROOT%\docker-compose.yml" stop db >nul 2>&1 && echo [OK] PostgreSQL zupyneno || echo [ ] Docker ne vidpovidaie
echo Gotovo.
goto :EOF

:: ── --logs ─────────────────────────────────────────────────────────────────
:LOGS
echo API log: %LOG_API%
echo Frontend log: %LOG_FRONT%
echo.
type "%LOG_API%" 2>nul
echo.
echo --- FRONTEND ---
type "%LOG_FRONT%" 2>nul
goto :EOF
