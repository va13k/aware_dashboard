#!/bin/bash
set -e

BASE="/home/ouesly/aware_dashboard"
MICRO="$BASE/aware-micro-server"
NGINX="$BASE/nginx"

echo "======================================"
echo " AWARE iOS ESM Setup Script"
echo "======================================"

echo ""
echo "[1/6] Creating iOS ESM config file..."
mkdir -p "$MICRO/esm"
cat > "$MICRO/esm/ios-esm-config.json" << 'EOF'
[
  {
    "schedule_id": "happy_check_v1",
    "hours": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23],
    "start_date": "04-28-2026",
    "end_date": "04-30-2026",
    "expiration": 4,
    "randomize": 0,
    "notification_title": "Quick question",
    "notification_body": "Tap to answer one question",
    "esms": [
      {
        "esm": {
          "esm_type": 2,
          "esm_title": "Are you happy?",
          "esm_instructions": "",
          "esm_radios": ["Yes", "No"],
          "esm_submit": "Submit",
          "esm_expiration_threshold": 4,
          "esm_trigger": "happy_check"
        }
      }
    ]
  }
]
EOF
echo "      OK ESM config file created"

echo ""
echo "[2/6] Updating aware-config.json..."
python3 << PYEOF
import json, sys
path = "$MICRO/aware-config.json"
with open(path) as f:
    config = json.load(f)
for p in config.get("plugins", []):
    if p.get("plugin") == "plugin_ios_esm":
        print("      SKIP iOS ESM plugin already exists")
        sys.exit(0)
for sensor in config.get("sensors", []):
    if sensor.get("sensor") == "esm":
        for s in sensor.get("settings", []):
            if s.get("setting") == "status_esm":
                s["defaultValue"] = "true"
config["plugins"].append({
    "package_name": "com.aware.plugin.ios_esm",
    "plugin": "plugin_ios_esm",
    "settings": [
        {"setting": "status_plugin_ios_esm", "title": "Active", "defaultValue": "true"},
        {"setting": "plugin_ios_esm_config_url", "title": "iOS ESM Config URL", "defaultValue": "http://dido.inf.usi.ch/esm/ios-esm-config.json"}
    ]
})
with open(path, "w") as f:
    json.dump(config, f, indent=2)
print("      OK aware-config.json updated")
PYEOF

echo ""
echo "[3/6] Adding esm volume to docker-compose.yml..."
if grep -q "ios-esm-config" "$BASE/docker-compose.yml"; then
    echo "      SKIP already present"
else
    sed -i 's|      - ./studies:/usr/share/nginx/html/studies:ro|      - ./studies:/usr/share/nginx/html/studies:ro\n      - ./aware-micro-server/esm:/usr/share/nginx/html/esm:ro|' "$BASE/docker-compose.yml"
    echo "      OK docker-compose.yml updated"
fi

echo ""
echo "[4/6] Adding /esm/ location to nginx http.conf..."
if grep -q "location /esm/" "$NGINX/http.conf"; then
    echo "      SKIP already present"
else
    cat >> "$NGINX/http.conf.tmp" << 'NGINXEOF'

    # iOS ESM config file
    location /esm/ {
        alias /usr/share/nginx/html/esm/;
        add_header Access-Control-Allow-Origin *;
    }
NGINXEOF
    # Insert before the last closing brace
    head -n -1 "$NGINX/http.conf" > "$NGINX/http.conf.new"
    cat "$NGINX/http.conf.tmp" >> "$NGINX/http.conf.new"
    echo "}" >> "$NGINX/http.conf.new"
    mv "$NGINX/http.conf.new" "$NGINX/http.conf"
    rm -f "$NGINX/http.conf.tmp"
    echo "      OK http.conf updated"
fi

echo ""
echo "[5/6] Recreating nginx only (safe - no --force-recreate on others)..."
cd "$BASE"
sudo docker compose up -d --no-deps nginx
echo "      OK nginx restarted"

echo ""
echo "[6/6] Restarting micro-server..."
sudo docker compose restart micro-server
echo "      OK micro-server restarted"

echo ""
echo "======================================"
echo " Testing in 5 seconds..."
echo "======================================"
sleep 5

HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://dido.inf.usi.ch/esm/ios-esm-config.json)

if [ "$HTTP_STATUS" = "200" ]; then
    echo ""
    echo "  SUCCESS! ESM file accessible at:"
    echo "  http://dido.inf.usi.ch/esm/ios-esm-config.json"
    echo ""
    echo "  Have iOS participants re-scan the QR code!"
else
    echo ""
    echo "  FAILED - HTTP $HTTP_STATUS"
    echo "  Run: sudo docker logs aware_nginx --tail 20"
fi

