@echo off
setlocal enabledelayedexpansion
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
    if errorlevel 1 exit /b 1
    python setup\init_android_tables.py
    if errorlevel 1 exit /b 1
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

rem Remove markers from any previous run
if exist .env.saved del .env.saved
if exist setup\.wizard_url del setup\.wizard_url

for /f "usebackq delims=" %%i in (`python setup\detect_public_host.py`) do set SUGGESTED_PUBLIC_HOST=%%i
(
    echo PUBLIC_HOST=%SUGGESTED_PUBLIC_HOST%
    echo PUBLIC_PORT=80
    echo PROTOCOL=http
) > .setup-defaults.env

docker compose --profile setup up --build -d setup-wizard
if errorlevel 1 exit /b 1

echo.
echo   Waiting for setup wizard to start...

rem Wait for server.py to write the token URL (up to 30 seconds)
set WIZARD_WAIT=0
:WAIT_WIZARD_URL
if exist setup\.wizard_url goto READ_WIZARD_URL
timeout /t 1 /nobreak >nul
set /a WIZARD_WAIT+=1
if %WIZARD_WAIT% lss 30 goto WAIT_WIZARD_URL
echo.
echo   ERROR: Could not read wizard URL.
echo   Check logs with: docker compose logs setup-wizard
echo.
pause
exit /b 1

:READ_WIZARD_URL
set /p TOKEN_PATH=<setup\.wizard_url
set WIZARD_URL=http://%SUGGESTED_PUBLIC_HOST%:9999%TOKEN_PATH%

echo.
echo   Setup wizard is ready. Open this URL in your browser:
echo.
echo     %WIZARD_URL%
echo.
echo   This token is valid for this session only. Keep it private.
echo.

start "" "%WIZARD_URL%"

echo   Fill in the form and click Save.
echo   Waiting for configuration...
echo.

:WAIT_ENV_SAVED
timeout /t 2 /nobreak >nul
if not exist .env.saved goto WAIT_ENV_SAVED
del .env.saved

echo   Configuration saved! Starting services...
echo.

docker compose --profile setup stop setup-wizard 2>nul
docker compose --profile setup rm -f setup-wizard 2>nul

docker compose up --build -d
if errorlevel 1 exit /b 1
python setup\init_android_tables.py
if errorlevel 1 exit /b 1

echo.
echo   All services are starting.
echo   Run 'docker compose ps' to check status.
echo   Run 'docker compose logs -f' to see logs.
echo.
pause
