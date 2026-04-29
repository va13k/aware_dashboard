# AWARE Dashboard — Security, Robustness & Data-Integrity Report

**Date:** 2026-04-29  
**Scope:** Full codebase audit — security vulnerabilities, data-loss risks, update protocol  
**Note:** This is a report only. No core code has been changed.

---

## Executive Summary

The stack has a solid foundation (parameterised queries via SQLAlchemy ORM, JWT-style HMAC session tokens, least-privilege MySQL users, token-gated setup wizard, security headers in Nginx) but several issues could allow a malicious actor to read the database credentials that are embedded in participant-facing files, brute-force the researcher login, or destroy all research data with a single accidental command.

Severity ratings used below: **CRITICAL / HIGH / MEDIUM / LOW**.

---

## Part 1 — Security Vulnerabilities

---

### [CRITICAL] S-1 · Database password embedded in Android study JSON files

**File:** `shared_config/serializers.py` lines 189–204, `AWARE-Configurator/App01/general.py` line 243  
**File served publicly at:** `nginx/http.conf` — location `/studies/files/` (no auth required)

The `serialize_android_config` function writes the Android participant database credentials — host, port, name, username, and **plaintext password** — into `studies/studyConfig.json`. Nginx serves everything under `/studies/files/` as static files with **no authentication**. Any person who knows (or guesses) the URL can download the file and use those credentials to connect directly to the MySQL database and INSERT arbitrary data.

**Why this is critical:** The study JSON is intended to be shared with Android participants. It must contain the database host and credentials so the AWARE Android app can upload data directly. This is the AWARE framework's architecture. But right now the files are world-readable on the server.

**Fix:**
1. Gate `/studies/files/` behind Nginx `auth_request /auth/validate;` — same as `/configurator/` — so only logged-in researchers can download study configs.
2. Alternatively, distribute study config files out-of-band (email to participants), remove them from the Nginx static directory, or use a time-limited signed URL.
3. At minimum, add a prominent warning in the README that `/studies/files/` must be firewall-restricted if the files contain live database credentials.

---

### [CRITICAL] S-2 · Hardcoded passwords across the default stack

**Files:** `db/create_dbs.sql`, `aware-micro-server/aware-config.example.json`

`db/create_dbs.sql` creates the participant MySQL users with the hardcoded passwords `participantpass` and `analyticspass`. These are baked into the Docker MySQL init scripts and will be used verbatim unless the operator explicitly changes them — which the setup wizard currently does **not** prompt for. `aware-config.example.json` also has `participantpass` as the iOS participant password.

Anyone who reads the public repository knows these passwords.

**Fix:**
1. Generate random passwords for `aware_android_participant`, `aware_ios_participant`, and `aware_analytics` at setup time (the way `DJANGO_SECRET_KEY` and `ANALYTICS_API_KEY` are already auto-generated).
2. Store them in `.env` and pass them through to the database init scripts and micro-server config.
3. Rotate them during any first-run that detects the `participantpass` default is still in use.

---

### [HIGH] S-3 · Session secret regenerated on every container restart

**File:** `analytics_api/app/routers/auth.py` line 16

```python
_SECRET = secrets.token_bytes(32)
```

A new HMAC secret is generated each time the `dashboard-api` container starts. Every in-memory researcher session is silently invalidated on restart (including for automated updates), and users are redirected to the login page. More importantly, if the secret were ever persisted in a predictable place or derived from a known value, session tokens could be forged.

**Fix:** Read `_SECRET` from a persistent env var (`SESSION_SECRET`) that is generated once at setup time (same pattern as `DJANGO_SECRET_KEY`) and written to `.env`. If the env var is absent, fall back to a random value but log a clear warning.

---

### [HIGH] S-4 · No brute-force protection on the login endpoint

**File:** `analytics_api/app/routers/auth.py` — `POST /auth/login`  
**File:** `nginx/http.conf` and `nginx/https.conf` — no rate-limit directive on `/auth/`

The login endpoint has no rate limiting, no lockout, and no CAPTCHA. An attacker who can reach the server can attempt passwords at the full speed of the network connection.

**Fix options (in order of ease):**
1. Add an Nginx `limit_req_zone` and `limit_req` directive on the `/auth/` location — 5–10 requests/minute per IP is enough to stop automated attacks without bothering researchers.
2. Add a short server-side delay on failed attempts (e.g., `asyncio.sleep(1)` after a failed check) in `auth.py`.
3. Both together.

Example Nginx snippet (add to the top of the `server` block):
```nginx
limit_req_zone $binary_remote_addr zone=auth:10m rate=5r/m;
# then inside location /auth/:
limit_req zone=auth burst=5 nodelay;
```

---

### [HIGH] S-5 · `source.json` contains database credentials in plaintext

**File:** `source.json` (project root)

`source.json` is the central configuration store used by the setup wizard, the configurator, and the serializers. It contains `database.android.password` and `database.ios.password` in plaintext. It is bind-mounted into the configurator container and the setup wizard container. There is no filesystem restriction on who can read it from the host.

**Fix:**
1. Restrict file permissions after generation: `chmod 600 source.json`.
2. Consider whether the database passwords need to live in `source.json` at all — they could be read from `.env` at runtime instead.
3. Add `source.json` to `.gitignore` (ensure it isn't accidentally committed).

---

### [HIGH] S-6 · Session cookie missing `Secure` flag in HTTPS mode

**File:** `analytics_api/app/routers/auth.py` line 87

```python
resp.set_cookie(_COOKIE, token, max_age=_MAX_AGE, httponly=True, samesite="lax")
```

The `secure=True` keyword argument is not set. When the server runs under HTTPS (the common production configuration), browsers will still send the cookie over plain HTTP if an attacker can downgrade the connection. The `Strict-Transport-Security` header in `https.conf` mitigates this for compliant browsers, but the cookie itself should be marked `Secure` as defence-in-depth.

**Fix:** Change the `set_cookie` call to:
```python
is_https = os.environ.get("PROTOCOL", "http") == "https"
resp.set_cookie(_COOKIE, token, max_age=_MAX_AGE, httponly=True, samesite="lax", secure=is_https)
```

---

### [MEDIUM] S-7 · SSL certificate verification disabled in Configurator DB connector

**File:** `AWARE-Configurator/App01/db.py` lines 11–14

```python
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.VerifyMode.CERT_NONE
```

The `check_hostname = False` and `CERT_NONE` combination completely disables TLS certificate verification when the configurator tests or initialises the Android database. An active network attacker between the configurator container and the MySQL host could present any certificate and intercept the connection.

**Fix:** Remove these two lines and use the default SSL context. For internal Docker networking (where MySQL is `mysql`), the container CA bundle may not contain the MySQL cert — in that case, mount the CA cert into the container and pass it via `ssl_ca` in the pymysql call.

---

### [MEDIUM] S-8 · `CSRF_EXEMPT` on database credential endpoints

**File:** `AWARE-Configurator/App01/database_operations.py` lines 13, 31

Both `test_connection` and `initialize_database` are decorated with `@csrf_exempt`. These endpoints accept database host, port, credentials, and a root password from the request body and perform live database operations with them. If a logged-in researcher's browser is tricked into visiting a malicious page, a CSRF attack could be used to probe or re-initialise arbitrary MySQL servers.

**Fix:** Remove `@csrf_exempt` from both endpoints. The React frontend already has CSRF token support via `get_token` (`@ensure_csrf_cookie`) — ensure the React calls include the `X-CSRFToken` header.

---

### [MEDIUM] S-9 · Health endpoint is unauthenticated and leaks internal error messages

**File:** `analytics_api/app/routers/health.py`

`GET /health` requires no API key and returns raw Python exception text when the DB is unreachable:
```python
results["android"] = str(e)
```
This can expose internal hostnames, driver version strings, or connection parameters to anyone who can reach the server.

**Fix:** Replace `str(e)` with a generic `"connection failed"` string. Move the detailed exception to the application log only. If you need the health endpoint to be callable by unauthenticated monitoring systems, that is fine, but sanitise the output.

---

### [MEDIUM] S-10 · `DJANGO_ALLOWED_HOSTS = "*"` in docker-compose.yml

**File:** `docker-compose.yml` line 65

```yaml
DJANGO_ALLOWED_HOSTS: "*"
```

This overrides the careful `_allowed_hosts()` logic in `settings.py` and disables Django's Host header validation entirely. An attacker can inject arbitrary `Host:` headers, which can be exploited for cache poisoning or password-reset link hijacking (less relevant here since there is no password reset, but it is a bad practice).

**Fix:** Remove this line. The `PUBLIC_HOST` env var is already propagated to the container, and `settings.py` derives `ALLOWED_HOSTS` from it correctly.

---

### [MEDIUM] S-11 · Setup wizard transmits MySQL root password over plain HTTP

**File:** `setup/server.py`, `setup/deploy.sh`, the wizard HTML form

The setup wizard runs on port 9999 over HTTP only. During the `POST /cgi-bin/deploy` call, the MySQL root password and researcher credentials are transmitted in the clear. If port 9999 is reachable over a network (required for headless Linux servers as documented), anyone with network access can intercept these credentials with a passive packet capture.

**Fix:**
1. Clearly document that port 9999 must only be accessed via an SSH tunnel (`ssh -L 9999:localhost:9999 ...`) and never opened to the internet.
2. Consider adding a reminder in the wizard UI itself: "You are connecting over HTTP. Use an SSH tunnel if you are not on localhost."

---

### [LOW] S-12 · `/studies/` index page contains the iOS study join URL without authentication

**File:** `studies/index.html` (generated), `nginx/http.conf` — location `/studies/`

The studies page is served without authentication and includes the iOS study QR code join URL and the path to the Android study config file. An attacker who finds this page can join the iOS study without being a legitimate participant and upload fabricated data.

This may be intentional (participants need to scan the QR code), but it is worth noting for study integrity.

**Fix:** If participant access to the join page should be controlled, protect `/studies/` with `auth_request` similarly to `/configurator/`. If the page must remain public, document that any person who finds it can join the study.

---

## Part 2 — Data Loss Risks

---

### [CRITICAL] D-1 · `docker compose down -v` destroys all research data

**File:** `README.md` — "Common Operations" section

The command `sudo docker compose down -v` is documented as "Stop and wipe all data (irreversible)". The `mysql_data` named volume holds all collected sensor data. A single accidental flag destroys months of research. There is currently no backup mechanism in the stack.

**Recommended backup strategy:**

**Option A — Daily `mysqldump` cron (simplest):**
```bash
# Run on the host, e.g., in /etc/cron.daily/aware-backup
#!/bin/sh
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=/opt/aware_backups
mkdir -p "$BACKUP_DIR"
sudo docker exec aware_mysql \
  mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" \
  --single-transaction --all-databases \
  | gzip > "$BACKUP_DIR/aware_$DATE.sql.gz"
# Keep last 30 days
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +30 -delete
```
Read `MYSQL_ROOT_PASSWORD` from `.env` before running.

**Option B — MySQL binary log + point-in-time recovery:**  
Add to a custom `mysql/my.cnf` mounted as a volume:
```ini
[mysqld]
log_bin = /var/lib/mysql/binlog
binlog_format = ROW
expire_logs_days = 14
```
This enables recovery to any point in the last 14 days, not just backup snapshots.

**Option C — Volume snapshot (best for large datasets):**  
Use `docker run --rm -v mysql_data:/data -v /opt/backups:/backup alpine tar czf /backup/mysql_$(date +%Y%m%d).tar.gz /data` to snapshot the raw InnoDB files.

At minimum, implement Option A and remove `docker compose down -v` from the documented "common operations" or replace it with a prominent warning box.

---

### [HIGH] D-2 · No health checks on `configurator` and `micro-server` — Nginx starts before they are ready

**File:** `docker-compose.yml` lines 96–102

```yaml
depends_on:
  configurator:
    condition: service_started   # ← not service_healthy
  micro-server:
    condition: service_started
```

`service_started` only means the container process was launched, not that the application is ready to accept connections. If Nginx starts accepting requests while the configurator or micro-server is still initialising (e.g., waiting for MySQL), requests fail with 502. During restarts, this window can be several seconds.

**Fix:** Add health checks to both services and change `depends_on` to `service_healthy`.

For `configurator`:
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health/"]
  interval: 10s
  timeout: 5s
  retries: 6
  start_period: 30s
```

For `micro-server`:
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8080/"]
  interval: 10s
  timeout: 5s
  retries: 6
  start_period: 30s
```

---

### [HIGH] D-3 · MySQL connection drops from micro-server during restart cause data loss

When `docker compose restart mysql` or a full stack restart occurs, the micro-server's existing MySQL connections are broken. The Vert.x connection pool will reconnect, but any INSERT that was in-flight at the moment of disconnection is silently dropped. The iOS AWARE client retries uploads, but there is a risk window.

**Fix:**
1. Configure the micro-server's connection pool with retry-on-failure and an exponential back-off reconnect policy (requires change in Kotlin code — noted as a code-level recommendation only).
2. For planned maintenance: stop the micro-server first (`sudo docker compose stop micro-server`), wait 30s for in-flight writes to complete, then restart MySQL, then restart micro-server.

---

### [MEDIUM] D-4 · `source.json` has no backup before the configurator overwrites it

**File:** `shared_config/source_store.py`

`source_store.py` uses `os.replace()` (atomic rename) for writes — this protects against corrupt partial writes but does not keep any history. If the configurator receives a malformed study config save, the previous study configuration is permanently overwritten with no recovery path.

**Fix:** Before `os.replace(tmp_path, SOURCE_PATH)`, copy the current file to `source.json.bak`:
```python
import shutil
if SOURCE_PATH.exists():
    shutil.copy2(SOURCE_PATH, SOURCE_PATH.with_suffix(".json.bak"))
os.replace(tmp_path, SOURCE_PATH)
```
This is a one-deep history, but it covers the most common "oops" scenario.

---

### [MEDIUM] D-5 · `aware-config.json` has no backup before it is overwritten

**File:** `shared_config/serializers.py` `write_micro_config` and `AWARE-Configurator/App01/general.py` `write_outputs`

Both the setup wizard and the configurator overwrite `aware-micro-server/aware-config.json` in-place without keeping a previous copy. If the iOS micro-server config is corrupted (e.g., if `source.json` is missing a required field), the micro-server will fail to restart and iOS data will be lost until the config is manually repaired.

**Fix:** Same pattern as D-4 — write to a `.bak` file before replacing.

---

### [LOW] D-6 · `write_json` in `general.py` is not atomic

**File:** `AWARE-Configurator/App01/general.py` lines 82–86

```python
def write_json(path, content):
    with open(path, 'w', encoding='utf-8') as file:
        json.dump(content, file, indent=2)
```

This opens the destination file for writing directly. If the process is killed mid-write, the file is left partially written and corrupt. This contrasts with `source_store.py` which correctly uses `tempfile.mkstemp` + `os.replace`.

**Fix:** Use the same atomic write pattern as `source_store._atomic_write_unlocked`.

---

## Part 3 — Update / Restart Protocol

---

### Recommended Zero-Data-Loss Update Procedure

When you need to update code and restart the stack, follow this order to minimise the window during which mobile clients cannot upload data:

```
Step 1: Drain the micro-server (iOS clients)
   sudo docker compose stop micro-server
   # Wait 30 seconds — lets in-flight iOS uploads finish
   # iOS AWARE clients will retry; the retry window is their configured
   # frequency_webservice (default: every 30 min), so short downtime is safe

Step 2: Drain the configurator (researcher traffic)
   sudo docker compose stop configurator
   # This has no effect on data collection

Step 3: Rebuild changed images (without stopping MySQL)
   sudo docker compose build configurator micro-server dashboard dashboard-api
   # MySQL stays running — all Android data continues to arrive uninterrupted
   # (Android AWARE uploads directly to MySQL, not through micro-server)

Step 4: Restart read-only services first
   sudo docker compose up -d dashboard-api dashboard

Step 5: Restart participant-facing services
   sudo docker compose up -d micro-server configurator

Step 6: Reload Nginx (zero-downtime config reload)
   sudo docker compose kill -s HUP nginx
   # HUP causes Nginx to reload config without dropping connections

Step 7: Verify
   sudo docker compose ps
   sudo docker compose logs --tail=50 micro-server
   sudo docker compose logs --tail=50 configurator
```

**Key principle:** Never restart MySQL during normal updates unless MySQL itself needs updating. MySQL handles millions of Android INSERTs while everything else restarts around it.

**When MySQL itself must be updated:**
```
Step 1: Stop micro-server (iOS) and wait 30s
Step 2: Take a mysqldump backup (see D-1 above)
Step 3: Stop configurator and dashboard-api
Step 4: sudo docker compose stop mysql
Step 5: sudo docker compose up -d mysql
Step 6: Wait for health check to pass:
        sudo docker compose ps  # mysql should show "(healthy)"
Step 7: Restart remaining services
        sudo docker compose up -d micro-server configurator dashboard-api dashboard
```

---

### Rollback Procedure

If the new version has a bug, roll back with:
```bash
# Stop broken services
sudo docker compose stop configurator micro-server dashboard dashboard-api

# Restore source.json from backup (if modified by the update)
cp source.json.bak source.json

# Rebuild from the previous Git commit
git checkout HEAD~1 -- AWARE-Configurator aware-micro-server analytics_api dashboard
sudo docker compose build configurator micro-server dashboard dashboard-api
sudo docker compose up -d configurator micro-server dashboard dashboard-api
```

---

## Part 4 — Additional Hardening Recommendations

These are not code vulnerabilities but operational practices that significantly improve the security posture for a live research deployment.

| # | Recommendation | Effort |
|---|---|---|
| H-1 | Enable HTTPS (`PROTOCOL=https`) with a Let's Encrypt certificate. All data in transit (including Android uploads to MySQL) will be protected by TLS. | Low |
| H-2 | Firewall the MySQL port (3306). MySQL should never be directly reachable from outside the Docker network. Confirm with `sudo ss -tlnp \| grep 3306` — it must not show `0.0.0.0:3306`. | Low |
| H-3 | Change the default participant passwords (`participantpass`, `analyticspass`) — see S-2. | Medium |
| H-4 | Set `RESEARCHER_PASSWORD` to a strong random value (at least 16 characters). The setup wizard auto-generates one, but verify it was not left as a weak default. | Low |
| H-5 | Rotate `ANALYTICS_API_KEY`, `DJANGO_SECRET_KEY`, and `SESSION_SECRET` (once added) every 6–12 months or after any suspected compromise. | Low |
| H-6 | Add `source.json`, `aware-micro-server/aware-config.json`, `.env`, and `studies/` to `.gitignore` if not already present. These files contain secrets and participant data. | Low |
| H-7 | Implement MySQL binary logging (see D-1 Option B) to enable point-in-time recovery. This is the most effective single safeguard against data loss. | Medium |
| H-8 | Consider encrypting the `mysql_data` Docker volume or the host filesystem directory that backs it (e.g., with `dm-crypt`/LUKS on Linux). This protects data if the server is physically seized or the disk is removed. | High |
| H-9 | Add the `studies/files/` location to Nginx auth_request (see S-1) before sharing any study config with participants. | Low |
| H-10 | Review whether the `telephony` table (which stores IMEI, subscriber ID, SIM serial, line number) and the `calls`/`messages`/`keyboard`/`screenshot` tables comply with your IRB data handling requirements and local privacy regulations. These are particularly sensitive. | Low (review only) |

---

## Summary Table

| ID | Severity | Area | Issue |
|---|---|---|---|
| S-1 | CRITICAL | Auth | Android study JSON with DB password served without auth |
| S-2 | CRITICAL | Secrets | Hardcoded `participantpass` / `analyticspass` in SQL init |
| S-3 | HIGH | Auth | Session HMAC secret regenerated on every container restart |
| S-4 | HIGH | Auth | No rate limiting on login endpoint |
| S-5 | HIGH | Secrets | `source.json` stores DB passwords in plaintext |
| S-6 | HIGH | Auth | Session cookie missing `Secure` flag in HTTPS mode |
| S-7 | MEDIUM | TLS | SSL certificate verification disabled in configurator DB connector |
| S-8 | MEDIUM | Auth | `@csrf_exempt` on database credential endpoints |
| S-9 | MEDIUM | Info leak | Health endpoint unauthenticated, leaks DB error messages |
| S-10 | MEDIUM | Config | `DJANGO_ALLOWED_HOSTS = "*"` disables Django host validation |
| S-11 | MEDIUM | Config | Setup wizard transmits secrets over HTTP on port 9999 |
| S-12 | LOW | Auth | Studies page (iOS join URL) accessible without authentication |
| D-1 | CRITICAL | Backup | No database backup strategy; `down -v` destroys all data |
| D-2 | HIGH | Reliability | No health checks; Nginx starts before services are ready |
| D-3 | HIGH | Reliability | MySQL restart causes in-flight iOS INSERT data loss |
| D-4 | MEDIUM | Backup | `source.json` overwritten with no backup copy |
| D-5 | MEDIUM | Backup | `aware-config.json` overwritten with no backup copy |
| D-6 | LOW | Reliability | `write_json` in general.py is not atomic |
