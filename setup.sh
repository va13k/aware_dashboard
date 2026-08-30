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

if ! sudo docker compose version > /dev/null 2>&1; then
    echo "  Docker Compose v2 is required but is not available."
    echo "  Update Docker, then rerun ./setup.sh."
    echo ""
    exit 1
fi

# Containers that write into bind-mounted host directories (e.g. the
# Configurator saving studyConfig.json / ios-esm-config.json) run as this
# UID:GID instead of root, so the files stay owned by whoever deployed the
# stack. Re-seeded on every run in case setup.sh is invoked by a different
# user than the one who deployed originally.
if [ -f .env ]; then
    # Without this check an unreadable .env yields an empty strip that still
    # replaces it, silently discarding every secret it held.
    if [ ! -r .env ]; then
        echo "  Cannot read .env — it is owned by another user (root?)."
        echo "  Fix its ownership, then rerun ./setup.sh."
        echo ""
        exit 1
    fi
    grep -v '^HOST_UID=\|^HOST_GID=' .env > .env.tmp || true
    mv .env.tmp .env
fi
# SUDO_UID/SUDO_GID keep the real user's ids under sudo, where id -u reports 0.
printf 'HOST_UID=%s\nHOST_GID=%s\n' "${SUDO_UID:-$(id -u)}" "${SUDO_GID:-$(id -g)}" >> .env

# Every compose invocation, with the override that takes the bundled database out
# of the deployment when the study names its own. deploy_config.py writes that file
# from the placement and removes it again, so its presence is the placement.
compose() {
    if [ -f docker-compose.external-db.yml ]; then
        sudo docker compose -f docker-compose.yml -f docker-compose.external-db.yml "$@"
    else
        sudo docker compose "$@"
    fi
}

# The containers whose health decides the browser may be redirected. The bundled
# database is one of them only when this deployment runs one.
health_checked_services() {
    if [ -f docker-compose.external-db.yml ]; then
        echo "aware_micro aware_configurator aware_dashboard_api aware_dashboard aware_nginx"
    else
        echo "aware_mysql aware_micro aware_configurator aware_dashboard_api aware_dashboard aware_nginx"
    fi
}

# The database is asked the same two questions whichever placement it runs: does it
# answer, and can this study write a row to it. An external one is asked before
# anything is generated; the bundled one only exists to be asked once it is up.
verify_database() {
    python3 setup/verify_database.py --docker-prefix sudo || true
}

deploy_stack() {
    mkdir -p studies aware-micro-server/cache aware-micro-server/esm
    python3 setup/deploy_config.py
    compose up --build -d
    python3 setup/init_study_tables.py --docker-prefix sudo
    verify_database
}

# The question a participant's phone will ask, asked before anyone enrols: the
# ingest endpoint at its public address, the certificate it presents, and a row
# posted the way the client posts one. A failure here is a study that looks
# deployed and collects nothing, so it is reported rather than exited on --- the
# stack is up either way, and the wizard shows the same result in the browser.
verify_ingest() {
    python3 setup/verify_ingest.py --docker-prefix sudo || true
}

print_deployment_links() {
    if [ ! -f deployment-urls.json ]; then
        return 0
    fi

    python3 - <<'PY'
import json
from pathlib import Path

labels = [
    ("App", "app_url"),
    ("Dashboard", "dashboard_url"),
    ("Configurator", "configurator_url"),
    ("Study links", "studies_url"),
]

try:
    urls = json.loads(Path("deployment-urls.json").read_text(encoding="utf-8"))
except Exception:
    urls = {}

if urls:
    print("  Access links:")
    for label, key in labels:
        value = urls.get(key)
        if value:
            print(f"    {label}: {value}")
PY
}

start_stack_only() {
    compose up --build -d
    python3 setup/init_study_tables.py --docker-prefix sudo
    verify_database
}

wait_for_service_redirect() {
    echo "  Waiting for services to become ready for browser redirect..."

    SERVICES=$(health_checked_services)
    EXPECTED=$(echo "$SERVICES" | wc -w | tr -d ' ')

    i=0
    while [ $i -lt 180 ]; do
        if sudo docker inspect \
            -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
            $SERVICES \
            2>/dev/null | awk -v want="$EXPECTED" '
                BEGIN { ok = 1; n = 0 }
                { n++ }
                $0 != "healthy" && $0 != "running" { ok = 0 }
                END { exit (ok && n == want) ? 0 : 1 }
            '; then
            echo "  Services are ready. Redirecting browser shortly..."
            sleep 5
            return 0
        fi

        sleep 2
        i=$((i + 1))
    done

    echo "  Services are still starting. The setup wizard will remain open."
    echo "  Run 'sudo docker compose ps' to check status."
    return 1
}

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
        echo "  Regenerating config and starting services..."
        echo ""
        deploy_stack
        verify_ingest
        echo ""
        echo "  All services are starting."
        print_deployment_links
        echo "  Run 'sudo docker compose ps' to check status."
        echo "  Run 'sudo docker compose logs -f' to see logs."
        echo ""
        exit 0
    fi
elif [ "$HAS_ENV" -eq 1 ] && [ "$HAS_MICRO_CONFIG" -eq 0 ]; then
    echo "  Found .env but no aware-micro-server/aware-config.json."
    echo "  Opening the setup wizard to finish the micro-server configuration."
    echo ""
fi

# Remove markers from any previous run
rm -f .env.saved setup/.wizard_url setup/.ingest-check.json setup/.database-check.json

SUGGESTED_PUBLIC_HOST=$(python3 setup/detect_public_host.py)
printf "PUBLIC_HOST=%s\nPUBLIC_PORT=80\nPROTOCOL=http\n" "$SUGGESTED_PUBLIC_HOST" > .setup-defaults.env

# Build and start the wizard
compose --profile setup up --build -d setup-wizard

echo ""
echo "  Waiting for setup wizard to start..."

# Wait for server.py to write the token URL (up to 30 seconds)
i=0
while [ ! -s setup/.wizard_url ] && [ $i -lt 30 ]; do
    sleep 1
    i=$((i + 1))
done

if [ ! -s setup/.wizard_url ]; then
    echo ""
    echo "  ERROR: Could not read wizard URL."
    echo "  Check logs with: sudo docker compose logs setup-wizard"
    echo ""
    exit 1
fi

TOKEN_PATH=$(cat setup/.wizard_url)
# The address this machine answers on, so a researcher deploying a server they are
# not sitting at can open the wizard from their own computer.
WIZARD_URL="http://${SUGGESTED_PUBLIC_HOST}:9999${TOKEN_PATH}"
echo ""
echo "  ┌──────────────────────────────────────────────────────────────┐"
echo "  │  Setup wizard is ready. Open this URL in your browser:      │"
echo "  │                                                              │"
printf "  │  %-60s  │\n" "$WIZARD_URL"
echo "  │                                                              │"
echo "  │  This token is valid for this session only.                 │"
echo "  └──────────────────────────────────────────────────────────────┘"
echo ""
# Said rather than assumed: the page behind that token carries this deployment's
# database password and the researcher's own, and it is served over plain HTTP.
echo "  Keep this URL to yourself — the page behind it holds this deployment's"
echo "  passwords. Port 9999 closes when setup finishes. On an untrusted network:"
echo "  put SETUP_BIND=127.0.0.1 in .env, then tunnel with"
echo "      ssh -N -L 9999:localhost:9999 ${SUDO_USER:-${USER:-user}}@${SUGGESTED_PUBLIC_HOST}"
echo ""

# Try to open browser
if command -v xdg-open > /dev/null 2>&1; then
    xdg-open "$WIZARD_URL" 2>/dev/null &
elif command -v open > /dev/null 2>&1; then
    open "$WIZARD_URL" &
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

# Start the actual services using the config already generated by the wizard
start_stack_only

if wait_for_service_redirect; then
    verify_ingest
    # Stop the wizard after the browser has had time to observe readiness and to
    # read the self-test result.
    sleep 3
    compose --profile setup stop setup-wizard 2>/dev/null
    compose --profile setup rm -f setup-wizard 2>/dev/null
    # The token goes with the server that honoured it, rather than staying
    # readable in the project folder for the life of the deployment.
    rm -f setup/.wizard_url
else
    verify_ingest
fi

echo ""
echo "  All services are starting."
print_deployment_links
echo "  Run 'sudo docker compose ps' to check status."
echo "  Run 'sudo docker compose logs -f' to see logs."
echo ""
