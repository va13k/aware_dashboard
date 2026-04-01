#!/bin/sh
set -e

echo ""
echo "  AWARE Dashboard Setup"
echo "  ─────────────────────"
echo ""

if ! command -v docker > /dev/null 2>&1; then
    echo "  Docker is required but was not found in PATH."
    echo "  Install Docker Desktop or Docker Engine, then rerun ./setup.sh."
    echo ""
    exit 1
fi

if ! docker compose version > /dev/null 2>&1; then
    echo "  Docker Compose v2 is required but is not available."
    echo "  Update Docker, then rerun ./setup.sh."
    echo ""
    exit 1
fi

HAS_ENV=0
HAS_MICRO_CONFIG=0

if [ -f .env ]; then
    HAS_ENV=1
fi

if [ -f aware-micro-server/aware-config.json ]; then
    HAS_MICRO_CONFIG=1
fi

# If setup is already complete, offer a choice
if [ "$HAS_ENV" -eq 1 ] && [ "$HAS_MICRO_CONFIG" -eq 1 ]; then
    echo "  Existing configuration found (.env)"
    echo ""
    echo "  1) Deploy with current config"
    echo "  2) Edit configuration first"
    echo ""
    printf "  Choose [1/2]: "
    read CHOICE

    if [ "$CHOICE" = "1" ]; then
        echo ""
        echo "  Starting services..."
        echo ""
        docker compose up --build -d
        echo ""
        echo "  All services are starting."
        echo "  Run 'docker compose ps' to check status."
        echo "  Run 'docker compose logs -f' to see logs."
        echo ""
        exit 0
    fi
elif [ "$HAS_ENV" -eq 1 ] && [ "$HAS_MICRO_CONFIG" -eq 0 ]; then
    echo "  Found .env but no aware-micro-server/aware-config.json."
    echo "  Opening the setup wizard to finish the micro-server configuration."
    echo ""
fi

# Remove marker from any previous run
rm -f .env.saved

# Build and start the wizard
docker compose --profile setup up --build -d setup-wizard

echo ""
echo "  Setup wizard is running."
echo ""
echo "  Open your browser to:  http://localhost:9999"
echo ""

# Try to open browser
if command -v xdg-open > /dev/null 2>&1; then
    xdg-open "http://localhost:9999" 2>/dev/null &
elif command -v open > /dev/null 2>&1; then
    open "http://localhost:9999" &
fi

echo "  Fill in the form and click Save."
echo "  Waiting for configuration..."
echo ""

# Wait for the marker file
while [ ! -f .env.saved ]; do
    sleep 2
done
rm -f .env.saved

echo "  Configuration saved! Starting services..."
echo ""

# Stop the wizard
docker compose --profile setup stop setup-wizard 2>/dev/null
docker compose --profile setup rm -f setup-wizard 2>/dev/null

# Start the actual services
docker compose up --build -d

echo ""
echo "  All services are starting."
echo "  Run 'docker compose ps' to check status."
echo "  Run 'docker compose logs -f' to see logs."
echo ""
