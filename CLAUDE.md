# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

AWARE Dashboard is a Docker-based research framework that collects sensor and survey data from Android and iOS devices. It bundles a study configurator, a mobile data server, an analytics API, a React dashboard, a shared MySQL database, and an Nginx reverse proxy into a single setup flow.

## Commands

### Start / deploy the full stack

```bash
./setup.sh           # first-time setup or reconfigure (opens wizard at :9999)
# or, if .env and aware-config.json already exist:
sudo docker compose up --build -d
python3 setup/init_android_tables.py --docker-prefix sudo
```

### Everyday operations

```bash
sudo docker compose logs -f                        # all services
sudo docker compose logs -f configurator           # single service
sudo docker compose restart configurator           # restart one service
sudo docker compose down                           # stop
sudo docker compose down -v                        # stop + wipe MySQL data (irreversible)
```

### Analytics API (analytics_api/) — local dev

```bash
cd analytics_api
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Requires `ANDROID_DATABASE_URL`, `IOS_DATABASE_URL`, and `ANALYTICS_API_KEY` env vars (see `env.example`).

### Dashboard (dashboard/) — local dev

```bash
cd dashboard
npm install
npm run dev       # Vite dev server
npm run build     # production build (tsc then vite build)
npm run lint      # ESLint
```

`VITE_API_KEY` is baked in at build time (Docker `--build-arg`), not a runtime env var. For local dev, put it in `dashboard/.env.local`.

### AWARE Configurator (AWARE-Configurator/) — local dev

```bash
cd AWARE-Configurator
pip install -r requirements.txt
cd reactapp && npm install && npm run build && cd ..
python manage.py runserver
```

Needs `DJANGO_SECRET_KEY` set; `PUBLIC_HOST` defaults to `localhost`. The Django server serves the pre-built React bundle from `reactapp/build/`.

### Micro server (aware-micro-server/) — build only

```bash
cd aware-micro-server
./gradlew build        # Kotlin/Gradle build
```

The micro-server is always run via Docker in this project. Config reloads live when `aware-config.json` changes (Docker Compose watch).

## Architecture

```
Nginx (:80/:443)
  ├── /configurator/     → AWARE-Configurator (Django + React)
  ├── /studies/          → static study JSON files
  ├── /api/              → analytics_api (FastAPI)
  ├── /dashboard/        → dashboard (React/Vite SPA)
  └── /:num/:key         → aware-micro-server (Kotlin/Vert.x, :8080/:8081 ws)
                                    ↓
                               MySQL :3306
                          aware_android / aware_ios
```

### Service summary

| Service | Tech | Role |
|---|---|---|
| `configurator` | Django + React | Android study builder; saves JSON configs to `studies/` |
| `aware-micro-server` | Kotlin + Vert.x | iOS participant-facing server; writes directly to `aware_ios` DB |
| `analytics_api` | FastAPI + SQLAlchemy (async) | Read-only sensor data API consumed by the dashboard |
| `dashboard` | React 19 + Vite + Tailwind v4 + Recharts | Researcher-facing data visualization UI |
| `mysql` | MySQL 8.0 | Shared database; `aware_android` and `aware_ios` schemas |
| `nginx` | nginx:alpine | Reverse proxy; switches between `http.conf` and `https.conf` via `PROTOCOL` |
| `setup-wizard` | Python (profile: setup) | One-time wizard that generates `.env` and `aware-config.json` |

### Key design decisions

- **Configurator has no database.** Android study configs are saved as JSON files in `studies/` and served statically by Nginx.
- **Analytics API has two separate SQLAlchemy engines** — `android_engine` and `ios_engine` — pointing to `aware_android` and `aware_ios` respectively.
- **`VITE_API_KEY` is a build-time arg**, not a runtime env var. Changing the API key requires rebuilding the `dashboard` container.
- **Micro-server config reloads live** — Docker Compose `watch` restarts the container whenever `aware-config.json` changes.
- **`shared_config/`** is a Python package mounted into the setup wizard and used by deploy scripts. `runtime.py` contains URL-building and `.env` normalization logic shared across setup, wizard, and deploy.

### MySQL users

| User | Access | Used by |
|---|---|---|
| `aware_android_participant` | INSERT on `aware_android` | Android AWARE client |
| `aware_ios_participant` | INSERT on `aware_ios` | AWARE Micro Server |
| `aware_analytics` | SELECT on both (container-restricted) | `analytics_api` |
| `root` | Full (password from `MYSQL_ROOT_PASSWORD`) | Init scripts only |

### Analytics API routing

All routes under `/android/{device_id}/<sensor>` and `/ios/{device_id}/<sensor>` require `X-API-Key` header. Query params: `from_ts`, `to_ts` (Unix float), `limit` (max 1000), `offset`.

### Environment variables (see `env.example`)

- `MYSQL_ROOT_PASSWORD`, `DJANGO_SECRET_KEY`, `ANALYTICS_API_KEY` — required secrets
- `PUBLIC_HOST`, `PUBLIC_PORT`, `PROTOCOL` — control all generated URLs and Nginx config
- `MICRO_DATABASE_HOST` — overrides the MySQL host seen by the micro-server (default: `mysql`)
- `ANDROID_DATABASE_HOST` — overrides the DB host embedded in Android study JSON files
- `SSL_CERTIFICATE_PATH`, `SSL_CERTIFICATE_KEY_PATH` — only needed when `PROTOCOL=https`

`DJANGO_ALLOWED_HOSTS` is derived from `PUBLIC_HOST` automatically; only override it if you need multiple hosts.
