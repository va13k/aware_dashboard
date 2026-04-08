@echo off
echo.
echo   AWARE Dashboard Setup
echo   ---------------------
echo.

docker compose version >nul 2>&1
if errorlevel 1 (
    echo   Docker with Compose v2 is required but was not found.
    echo   Install Docker Desktop, then rerun setup.bat.
    echo.
    pause
    exit /b 1
)

if not exist studies mkdir studies
if not exist aware-micro-server\cache mkdir aware-micro-server\cache

set HAS_ENV=0
set HAS_MICRO_CONFIG=0

if exist .env set HAS_ENV=1
if exist aware-micro-server\aware-config.json set HAS_MICRO_CONFIG=1

if "%HAS_ENV%"=="0" goto NO_ENV
if "%HAS_MICRO_CONFIG%"=="0" goto MISSING_MICRO_CONFIG

echo   Existing configuration found (.env)
echo.
echo   1) Deploy with current config
echo   2) Edit configuration first
echo.
set /p CHOICE="  Choose [1/2]: "

if "%CHOICE%"=="1" (
    echo.
    echo   Regenerating config and starting services...
    echo.
    python setup\deploy_config.py
    if errorlevel 1 exit /b 1
    docker compose up --build -d
    echo.
    echo   All services are starting.
    echo   Run 'docker compose ps' to check status.
    echo   Run 'docker compose logs -f' to see logs.
    echo.
    pause
    exit /b 0
)

:MISSING_MICRO_CONFIG
echo   Found .env but no aware-micro-server\aware-config.json.
echo   Opening the setup wizard to finish the micro-server configuration.
echo.

:NO_ENV

REM Remove marker from any previous run
if exist .env.saved del .env.saved

docker compose --profile setup up --build -d setup-wizard

echo   Setup wizard is running.
echo.
echo   Open your browser to:  http://localhost:9999
echo.

start http://localhost:9999

echo   Fill in the form and click Save.
echo   Waiting for configuration...
echo.

:WAIT_LOOP
timeout /t 2 /nobreak >nul
if not exist .env.saved goto WAIT_LOOP
del .env.saved

echo   Configuration saved! Starting services...
echo.

docker compose --profile setup stop setup-wizard 2>nul
docker compose --profile setup rm -f setup-wizard 2>nul

python setup\deploy_config.py
if errorlevel 1 exit /b 1
docker compose up --build -d

echo.
echo   All services are starting.
echo   Run 'docker compose ps' to check status.
echo   Run 'docker compose logs -f' to see logs.
echo.
pause
