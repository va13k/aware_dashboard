#!/bin/sh

# ── GET: load existing .env ──
if [ "$REQUEST_METHOD" = "GET" ]; then
    printf "Content-Type: application/json\r\n\r\n"

    if [ -f "$HOST_PROJECT_DIR/.env" ]; then
        MYSQL_PASS=""
        DJANGO_KEY=""
        DJANGO_HOSTS=""
        PROTOCOL=""
        SSL_CERT=""
        SSL_KEY=""
        while IFS='=' read -r key value; do
            case "$key" in
                MYSQL_ROOT_PASSWORD) MYSQL_PASS="$value" ;;
                DJANGO_SECRET_KEY) DJANGO_KEY="$value" ;;
                DJANGO_ALLOWED_HOSTS) DJANGO_HOSTS="$value" ;;
                PROTOCOL) PROTOCOL="$value" ;;
                SSL_CERTIFICATE_PATH) SSL_CERT="$value" ;;
                SSL_CERTIFICATE_KEY_PATH) SSL_KEY="$value" ;;
            esac
        done < "$HOST_PROJECT_DIR/.env"
        printf '{"exists":true,"MYSQL_ROOT_PASSWORD":"%s","DJANGO_SECRET_KEY":"%s","DJANGO_ALLOWED_HOSTS":"%s","PROTOCOL":"%s","SSL_CERTIFICATE_PATH":"%s","SSL_CERTIFICATE_KEY_PATH":"%s"}' \
            "$MYSQL_PASS" "$DJANGO_KEY" "$DJANGO_HOSTS" "$PROTOCOL" "$SSL_CERT" "$SSL_KEY"
    else
        printf '{"exists":false}'
    fi
    exit 0
fi

# ── POST: write .env and start build in background ──
BODY=$(cat)

ENV_CONTENT=$(echo "$BODY" | sed 's/.*"env":"//;s/"[^"]*$//' | sed 's/\\n/\
/g')

printf "%s\n" "$ENV_CONTENT" > "$HOST_PROJECT_DIR/.env"

# Clean up previous run
rm -f /tmp/deploy.done /tmp/deploy.running /tmp/compose.log

# Start build in background
touch /tmp/deploy.running
(
    COMPOSE_FILE="$HOST_PROJECT_DIR/docker-compose.yml" docker compose \
        --project-directory "$HOST_PROJECT_DIR" \
        up --build -d mysql micro-server configurator nginx > /tmp/compose.log 2>&1
    echo $? > /tmp/deploy.done
    rm -f /tmp/deploy.running
) </dev/null &

# Return immediately
printf "Content-Type: application/json\r\n\r\n"
printf '{"status":"started"}'
