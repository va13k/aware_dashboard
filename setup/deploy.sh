#!/bin/sh

# GET: load existing .env
if [ "$REQUEST_METHOD" = "GET" ]; then
    printf "Content-Type: application/json\r\n\r\n"

    if [ -f /project/.env ]; then
        MYSQL_PASS=""
        DJANGO_KEY=""
        DJANGO_HOSTS=""
        PUBLIC_HOST=""
        PUBLIC_PORT=""
        PROTOCOL=""
        SSL_CERT=""
        SSL_KEY=""
        while IFS='=' read -r key value; do
            case "$key" in
                MYSQL_ROOT_PASSWORD) MYSQL_PASS="$value" ;;
                DJANGO_SECRET_KEY) DJANGO_KEY="$value" ;;
                DJANGO_ALLOWED_HOSTS) DJANGO_HOSTS="$value" ;;
                PUBLIC_HOST) PUBLIC_HOST="$value" ;;
                PUBLIC_PORT) PUBLIC_PORT="$value" ;;
                PROTOCOL) PROTOCOL="$value" ;;
                SSL_CERTIFICATE_PATH) SSL_CERT="$value" ;;
                SSL_CERTIFICATE_KEY_PATH) SSL_KEY="$value" ;;
            esac
        done < /project/.env
        printf '{"exists":true,"MYSQL_ROOT_PASSWORD":"%s","DJANGO_SECRET_KEY":"%s","DJANGO_ALLOWED_HOSTS":"%s","PUBLIC_HOST":"%s","PUBLIC_PORT":"%s","PROTOCOL":"%s","SSL_CERTIFICATE_PATH":"%s","SSL_CERTIFICATE_KEY_PATH":"%s"}' \
            "$MYSQL_PASS" "$DJANGO_KEY" "$DJANGO_HOSTS" "$PUBLIC_HOST" "$PUBLIC_PORT" "$PROTOCOL" "$SSL_CERT" "$SSL_KEY"
    else
        printf '{"exists":false}'
    fi
    exit 0
fi

# POST: write .env and generate the micro-server config
BODY=$(cat)

ENV_CONTENT=$(printf "%s" "$BODY" | python3 -c 'import json, sys; print(json.load(sys.stdin)["env"])')

printf "%s\n" "$ENV_CONTENT" > /project/.env
mkdir -p /project/studies /project/aware-micro-server/cache

python3 - <<'PY'
import json
import pathlib
import secrets

project = pathlib.Path("/project")
env_path = project / ".env"
config_path = project / "aware-micro-server" / "aware-config.json"
example_path = project / "aware-micro-server" / "aware-config.example.json"

env = {}
for line in env_path.read_text(encoding="utf-8").splitlines():
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    env[key] = value

protocol = env.get("PROTOCOL", "http")
public_host = env.get("PUBLIC_HOST", "localhost")
public_port = int(env.get("PUBLIC_PORT", "443" if protocol == "https" else "80"))

source_path = config_path if config_path.exists() else example_path
config = json.loads(source_path.read_text(encoding="utf-8"))

server = config.setdefault("server", {})
server["database_engine"] = "mysql"
server["database_host"] = "mysql"
server["database_name"] = "aware_ios"
server["database_user"] = "aware_participant"
server["database_pwd"] = "participantpass"
server["database_port"] = 3306
server["server_host"] = "0.0.0.0"
server["server_port"] = 8080
server["websocket_port"] = 8081
server["external_server_host"] = f"{protocol}://{public_host}"
server["external_server_port"] = public_port
server["path_fullchain_pem"] = ""
server["path_key_pem"] = ""

study = config.setdefault("study", {})
study["study_number"] = study.get("study_number", 1)
study_key = str(study.get("study_key", "")).strip()
if not study_key or study_key in {"your_study_key", "CHANGE_ME"}:
    study["study_key"] = secrets.token_hex(6)

config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
PY

touch /project/.env.saved

printf "Content-Type: application/json\r\n\r\n"
printf '{"success":true}'
