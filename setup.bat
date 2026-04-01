@echo off
echo.
echo   AWARE Dashboard Setup
echo   ---------------------
echo.

docker compose --profile setup up --build -d setup-wizard

echo   Setup wizard is running.
echo.
echo   Open your browser to:  http://localhost:9999
echo.

start http://localhost:9999

echo   Fill in the form and click Deploy.
echo   You can come back to http://localhost:9999 anytime to edit settings.
echo.
echo   Press Ctrl+C to stop the setup wizard.
echo.

docker compose --profile setup logs -f setup-wizard 2>nul

docker compose --profile setup stop setup-wizard 2>nul
docker compose --profile setup rm -f setup-wizard 2>nul