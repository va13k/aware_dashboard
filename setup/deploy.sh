#!/bin/sh

# GET: load existing .env
if [ "$REQUEST_METHOD" = "GET" ]; then
    printf "Content-Type: application/json\r\n\r\n"

    if [ -f /project/.env ]; then
        MYSQL_PASS=""
        PUBLIC_HOST=""
        PUBLIC_PORT=""
        PROTOCOL=""
        SSL_CERT=""
        SSL_KEY=""
        while IFS='=' read -r key value; do
            case "$key" in
                MYSQL_ROOT_PASSWORD) MYSQL_PASS="$value" ;;
                PUBLIC_HOST) PUBLIC_HOST="$value" ;;
                PUBLIC_PORT) PUBLIC_PORT="$value" ;;
                PROTOCOL) PROTOCOL="$value" ;;
                SSL_CERTIFICATE_PATH) SSL_CERT="$value" ;;
                SSL_CERTIFICATE_KEY_PATH) SSL_KEY="$value" ;;
            esac
        done < /project/.env
        printf '{"exists":true,"MYSQL_ROOT_PASSWORD":"%s","PUBLIC_HOST":"%s","PUBLIC_PORT":"%s","PROTOCOL":"%s","SSL_CERTIFICATE_PATH":"%s","SSL_CERTIFICATE_KEY_PATH":"%s"}' \
            "$MYSQL_PASS" "$PUBLIC_HOST" "$PUBLIC_PORT" "$PROTOCOL" "$SSL_CERT" "$SSL_KEY"
    else
        printf '{"exists":false}'
    fi
    exit 0
fi

# POST: write .env and generate the micro-server config
BODY=$(cat)

ENV_CONTENT=$(printf "%s" "$BODY" | python3 -c 'import json, sys; print(json.load(sys.stdin)["env"])')
REQUEST_ENV_PATH=/tmp/aware-dashboard-request.env
printf "%s\n" "$ENV_CONTENT" > "$REQUEST_ENV_PATH"
mkdir -p /project/studies /project/aware-micro-server/cache

python3 /wizard/deploy_config.py

rm -f "$REQUEST_ENV_PATH"

touch /project/.env.saved

printf "Content-Type: application/json\r\n\r\n"
printf '{"success":true}'
