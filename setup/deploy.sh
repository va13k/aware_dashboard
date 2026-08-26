#!/bin/sh
set -e

trim_cr() {
    printf "%s" "$1" | tr -d '\r'
}

# An error reaches the browser as JSON. The message is encoded rather than
# interpolated, so a multi-line traceback, quotes and percent signs all arrive
# intact and the page can show what actually went wrong.
fail() {
    printf "Content-Type: application/json\r\n\r\n"
    ERROR_MSG="$1" python3 -c 'import json, os; print(json.dumps({"success": False, "error": os.environ["ERROR_MSG"]}))'
    exit 0
}

# GET: load existing .env
if [ "$REQUEST_METHOD" = "GET" ]; then
    printf "Content-Type: application/json\r\n\r\n"

    MYSQL_PASS=""
    SUGGESTED_PUBLIC_HOST=""
    PUBLIC_HOST=""
    PUBLIC_PORT=""
    PROTOCOL=""
    SSL_CERT=""
    SSL_KEY=""
    MYSQL_BACKUP_HOST_DIR="./backups/mysql"
    MYSQL_BACKUP_INTERVAL_SECONDS="86400"
    MYSQL_BACKUP_RETENTION_DAYS="30"
    RESEARCHER_USERNAME=""
    PARTICIPANT_DB_PASSWORD=""
    EXISTS=false

    if [ -f /project/.setup-defaults.env ]; then
        while IFS='=' read -r key value; do
            key=$(trim_cr "$key")
            value=$(trim_cr "$value")
            case "$key" in
                PUBLIC_HOST)
                    SUGGESTED_PUBLIC_HOST="$value"
                    PUBLIC_HOST="$value"
                    ;;
                PUBLIC_PORT) PUBLIC_PORT="$value" ;;
                PROTOCOL) PROTOCOL="$value" ;;
            esac
        done < /project/.setup-defaults.env
    fi

    if [ -f /project/.env ]; then
        EXISTS=true
        while IFS='=' read -r key value; do
            key=$(trim_cr "$key")
            value=$(trim_cr "$value")
            case "$key" in
                MYSQL_ROOT_PASSWORD) MYSQL_PASS="$value" ;;
                PUBLIC_HOST) PUBLIC_HOST="$value" ;;
                PUBLIC_PORT) PUBLIC_PORT="$value" ;;
                PROTOCOL) PROTOCOL="$value" ;;
                MYSQL_BACKUP_HOST_DIR) MYSQL_BACKUP_HOST_DIR="$value" ;;
                MYSQL_BACKUP_INTERVAL_SECONDS) MYSQL_BACKUP_INTERVAL_SECONDS="$value" ;;
                MYSQL_BACKUP_RETENTION_DAYS) MYSQL_BACKUP_RETENTION_DAYS="$value" ;;
                SSL_CERTIFICATE_PATH) SSL_CERT="$value" ;;
                SSL_CERTIFICATE_KEY_PATH) SSL_KEY="$value" ;;
                RESEARCHER_USERNAME) RESEARCHER_USERNAME="$value" ;;
                PARTICIPANT_DB_PASSWORD) PARTICIPANT_DB_PASSWORD="$value" ;;
            esac
        done < /project/.env
    fi

    printf '{"exists":%s,"MYSQL_ROOT_PASSWORD":"%s","SUGGESTED_PUBLIC_HOST":"%s","PUBLIC_HOST":"%s","PUBLIC_PORT":"%s","PROTOCOL":"%s","MYSQL_BACKUP_HOST_DIR":"%s","MYSQL_BACKUP_INTERVAL_SECONDS":"%s","MYSQL_BACKUP_RETENTION_DAYS":"%s","SSL_CERTIFICATE_PATH":"%s","SSL_CERTIFICATE_KEY_PATH":"%s","RESEARCHER_USERNAME":"%s","PARTICIPANT_DB_PASSWORD":"%s"}' \
        "$EXISTS" "$MYSQL_PASS" "$SUGGESTED_PUBLIC_HOST" "$PUBLIC_HOST" "$PUBLIC_PORT" "$PROTOCOL" "$MYSQL_BACKUP_HOST_DIR" "$MYSQL_BACKUP_INTERVAL_SECONDS" "$MYSQL_BACKUP_RETENTION_DAYS" "$SSL_CERT" "$SSL_KEY" "$RESEARCHER_USERNAME" "$PARTICIPANT_DB_PASSWORD"
    exit 0
fi

# POST: write .env and generate the micro-server config
BODY=$(cat)

REQUEST_ENV_PATH=/tmp/aware-dashboard-request.env
if ! ERROR_MSG=$(printf "%s" "$BODY" | python3 /wizard/write_request_env.py "$REQUEST_ENV_PATH" 2>&1); then
    fail "$ERROR_MSG"
fi

mkdir -p /project/studies /project/aware-micro-server/cache /project/aware-micro-server/esm

if ! ERROR_MSG=$(python3 /wizard/deploy_config.py 2>&1); then
    fail "$ERROR_MSG"
fi

rm -f "$REQUEST_ENV_PATH"

touch /project/.env.saved

RESEARCHER_USERNAME=""
RESEARCHER_PASSWORD=""
PARTICIPANT_DB_PASSWORD=""
if [ -f /project/.env ]; then
    while IFS='=' read -r key value; do
        key=$(trim_cr "$key")
        value=$(trim_cr "$value")
        case "$key" in
            RESEARCHER_USERNAME) RESEARCHER_USERNAME="$value" ;;
            RESEARCHER_PASSWORD) RESEARCHER_PASSWORD="$value" ;;
            PARTICIPANT_DB_PASSWORD) PARTICIPANT_DB_PASSWORD="$value" ;;
        esac
    done < /project/.env
fi

printf "Content-Type: application/json\r\n\r\n"
RESEARCHER_USERNAME="$RESEARCHER_USERNAME" \
RESEARCHER_PASSWORD="$RESEARCHER_PASSWORD" \
PARTICIPANT_DB_PASSWORD="$PARTICIPANT_DB_PASSWORD" \
python3 /wizard/deploy_response.py
