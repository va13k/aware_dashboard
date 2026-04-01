#!/bin/sh
set -e

echo ""
echo "  AWARE Dashboard Setup"
echo "  ─────────────────────"
echo ""

# Build and start the setup wizard
docker compose --profile setup up --build -d setup-wizard

echo "  Setup wizard is running."
echo ""
echo "  Open your browser to:  http://localhost:9999"
echo ""

# Try to open browser automatically
if command -v xdg-open > /dev/null 2>&1; then
    xdg-open "http://localhost:9999" 2>/dev/null &
elif command -v open > /dev/null 2>&1; then
    open "http://localhost:9999" &
fi

echo "  Fill in the form and click Deploy."
echo "  You can come back to http://localhost:9999 anytime to edit settings."
echo ""
echo "  Press Ctrl+C to stop the setup wizard."
echo ""

# Follow logs until user stops with Ctrl+C
docker compose --profile setup logs -f setup-wizard 2>/dev/null || true

# Clean up the wizard container when done
docker compose --profile setup stop setup-wizard 2>/dev/null
docker compose --profile setup rm -f setup-wizard 2>/dev/null