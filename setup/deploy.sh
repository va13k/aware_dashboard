#!/bin/sh
set -e

trim_cr() {
    printf "%s" "$1" | tr -d '\r'
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
                SSL_CERTIFICATE_PATH) SSL_CERT="$value" ;;
                SSL_CERTIFICATE_KEY_PATH) SSL_KEY="$value" ;;
            esac
        done < /project/.env
    fi

    printf '{"exists":%s,"MYSQL_ROOT_PASSWORD":"%s","SUGGESTED_PUBLIC_HOST":"%s","PUBLIC_HOST":"%s","PUBLIC_PORT":"%s","PROTOCOL":"%s","SSL_CERTIFICATE_PATH":"%s","SSL_CERTIFICATE_KEY_PATH":"%s"}' \
        "$EXISTS" "$MYSQL_PASS" "$SUGGESTED_PUBLIC_HOST" "$PUBLIC_HOST" "$PUBLIC_PORT" "$PROTOCOL" "$SSL_CERT" "$SSL_KEY"
    exit 0
fi

# POST: write .env and generate the micro-server config
BODY=$(cat)

REQUEST_ENV_PATH=/tmp/aware-dashboard-request.env
if ! ERROR_MSG=$(printf "%s" "$BODY" | python3 /wizard/write_request_env.py "$REQUEST_ENV_PATH" 2>&1); then
    printf "Content-Type: application/json\r\n\r\n"
    printf '{"success":false,"error":"%s"}' "$ERROR_MSG"
    exit 0
fi

mkdir -p /project/studies /project/aware-micro-server/cache

if ! ERROR_MSG=$(python3 /wizard/deploy_config.py 2>&1); then
    printf "Content-Type: application/json\r\n\r\n"
    printf '{"success":false,"error":"%s"}' "$ERROR_MSG"
    exit 0
fi

rm -f "$REQUEST_ENV_PATH"

touch /project/.env.saved

printf "Content-Type: application/json\r\n\r\n"
printf '{"success":true}'
