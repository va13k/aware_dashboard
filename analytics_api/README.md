# Analytics API

The read layer over the data AWARE phones upload. It turns the two MySQL
databases the mobile clients write into — `aware_android` and `aware_ios` — into
the JSON, CSV and ZIP the Analytics Dashboard displays and researchers download.

It is a FastAPI service. In a deployment it runs as the `dashboard-api`
container and is reached through Nginx at `/api/`; nothing needs to be installed
on the host to run the stack (see the [root README](../README.md)). This document
is for working on the service itself.

---

## What it is responsible for

| Area                     | What it provides                                                                                             |
| ------------------------ | ------------------------------------------------------------------------------------------------------------ |
| **Device inventory**     | Which phones exist, when each last uploaded, and where each stands in the study                              |
| **Sensor reads**         | Raw rows for one phone and one sensor over a time window                                                     |
| **Chart series**         | The same windows aggregated server-side into a fixed number of buckets, so a wide range stays a small response |
| **Record counts**        | Exact per-sensor, per-phone row counts, cached so the dashboard never runs `COUNT(*)` on a live table         |
| **Study state**          | A phone's enrolment derived from its study event log, and how the config it carries differs from the deployed one |
| **Client logs**          | The diagnostic lines Android clients report about their own operation                                         |
| **Exports**              | CSV for one sensor, ZIP bundles per device or per sensor, and a manifest of what exists                       |
| **Backup**               | Whole-database or single-period export, and import in either replace or merge mode                           |
| **Job progress**         | Status for work that runs longer than a request, so a page can show a progress bar                            |
| **Login**               | The session check Nginx calls before it lets anything through to `/api/`                                      |

It only ever **reads** study data. The database user it connects as
(`aware_analytics`) has `SELECT` on the sensor tables and write access to the
API's own tables and no others: `record_counts`, `coverage_hourly` and
`device_enrolment`, each derived from the study data rather than added to it.
Phones write their data through the separate AWARE Micro server, not through this
service.

---

## How it fits together

```
phones ──▶ micro-server ──▶ MySQL ◀── analytics_api ◀── Nginx /api/ ◀── dashboard
                             │              │
                  aware_android         reads only, plus
                  aware_ios             its own derived tables
```

Everything under `/api/` sits behind researcher login: Nginx asks
`GET /auth/validate` before proxying, and redirects to `/auth/login` when there
is no valid session. That applies to every endpoint below.

---

## The API surface

114 endpoints. The auto-generated OpenAPI pages (`/docs`, `/redoc`,
`/openapi.json`) are currently **disabled** in `app/main.py`, so this table is
the reference.

| Route                                        | Purpose                                                          |
| -------------------------------------------- | ---------------------------------------------------------------- |
| `GET /devices`                               | Every phone on both platforms                                    |
| `GET /devices/android`, `GET /devices/ios`   | One platform's phones                                            |
| `GET /devices/{platform}/{device_id}`        | One phone: metadata, per-sensor counts, study state, config diff  |
| `GET /devices/android/{device_id}/study-events` | The phone's study event history, paginated                    |
| `GET /android/{device_id}/{sensor}`          | Raw rows for one sensor — 36 sensors on Android, 45 on iOS        |
| `GET /android/{device_id}/{sensor}/series`   | The same window aggregated into ~1500 buckets, for charts         |
| `POST /android/{device_id}/export`           | Start an Android CSV export and get a job id back                 |
| `GET /android/{device_id}/export`            | Stream that CSV                                                   |
| `GET /ios/{device_id}/export`                | iOS CSV for one sensor — no job, so no progress to poll           |
| `GET /export/manifest`                       | What data exists, per platform and sensor                         |
| `GET /export/device/{platform}/{id}.zip`     | Every sensor for one phone, as a ZIP of CSVs                      |
| `GET /export/sensor/{platform}/{sensor}.zip` | One sensor across every phone                                     |
| `GET /export/all.zip`                        | Everything                                                        |
| `GET /logs/android`                          | Android client log lines, filtered and paginated                  |
| `GET /logs/android/log-types`                | The log categories present                                        |
| `GET /logs/android/export`                   | Those log lines as CSV                                            |
| `GET /backup/coverage`                       | Which periods hold data, so the page can offer only useful ones   |
| `POST /backup/export`                        | Start a database export; a period is optional                     |
| `GET /backup/export/{job_id}/download`       | Stream that archive                                               |
| `GET /backup/files`                          | Archives already on the server, offered as import sources         |
| `POST /backup/import`                        | Import an archive, replacing or merging                           |
| `GET /jobs/{job_id}`                         | Progress for any long-running job                                 |
| `POST /counts/refresh`, `POST /counts/reset` | Maintenance for the record-count cache                            |
| `GET /study/requirements`                    | Which sensors the deployed study config expects to receive        |
| `GET /health`                                | Liveness, used by the container healthcheck                       |
| `/auth/login`, `/auth/logout`, `/auth/validate` | Session handling for the Nginx login check                     |

The per-sensor routes are the bulk of the count and all share one shape: a
`device_id` in the path, a sensor slug, and `from_ts` / `to_ts` / `limit` query
parameters.

---

## Layout

| Path             | What lives there                                                            |
| ---------------- | --------------------------------------------------------------------------- |
| `app/routers/`   | HTTP endpoints, one module per area                                         |
| `app/services/`  | The logic the routers call. No FastAPI types below this line                 |
| `app/models.py`  | SQLAlchemy models mirroring the tables defined in `db/*.sql`                 |
| `app/schemas.py` | Pydantic models shaping what leaves the API                                  |
| `app/database.py`| The two async engines and their session factories                            |
| `tests/`         | Both test tiers                                                              |

The services, roughly in the order a newcomer meets them:

| Module                   | What it does                                                          |
| ------------------------ | --------------------------------------------------------------------- |
| `series.py`              | Bucketed aggregation, and the window clamping every read goes through |
| `record_counts.py`       | The per-sensor, per-phone count cache and its incremental refresh     |
| `coverage_rollup.py`     | How many records arrived per table, per phone, per hour                |
| `enrolment.py`           | When each phone was in the study, stored as windows (Android only)     |
| `study_state.py`         | Derives enrolment from a phone's study event log                      |
| `study_config.py`        | Reads study configs and redacts the credentials they contain          |
| `config_diff.py`         | Compares the config a phone carries against the deployed one          |
| `sensor_requirements.py` | Maps config settings to the sensor streams the API exposes            |
| `micro_config.py`        | Reads the settings iPhones are configured from                        |
| `coverage.py`            | Which periods hold data                                               |
| `dump_stream.py`         | Rewrites a mysqldump stream during a merge import                     |
| `watermarks.py`          | The newest stored timestamp per table and phone                       |
| `backup_jobs.py`         | Progress records for long-running work                                |

---

## Conventions worth knowing early

- **Timestamps are milliseconds** since the epoch, held as `DOUBLE`. Some older
  rows hold seconds; anything below `1e11` is treated as seconds.
- **Reads are bounded.** `services/series.py` clamps every window: a missing end
  becomes now, a missing start becomes a year before the end, and any window
  wider than a year is trimmed from the older end. An unbounded range scan over a
  high-rate sensor is not something a request is allowed to do.
- **Counts come from the cache, not from the tables.** `record_counts` is
  refreshed off the request path — by `POST /counts/refresh` or
  `python -m app.refresh_counts` from cron.
- **`_id` is exposed as `id`.** It is a per-deployment auto-increment key, so it
  identifies a row within one server and nothing across two.
- **Study configs hold credentials.** `aware_studies.study_config` contains
  participant and database passwords in full. Everything that returns a config
  goes through `services/study_config.py`, which redacts them.
- **Long work reports through a job**, not a held-open request: the caller starts
  it, gets an id, and polls `GET /jobs/{id}`.

---

## Running the tests

Two tiers. The first needs nothing installed; the second needs a local MySQL.

### Fast suite — the default

```bash
cd analytics_api && ../.venv/bin/python -m pytest
```

345 tests in about a second. These replace the database with a stand-in session,
so they cover logic, request wiring and response shapes without MySQL.

### Integration suite

```bash
cd analytics_api && ../.venv/bin/python -m pytest -m integration
```

These start a temporary MySQL, load the deployed schema from `db/init_all.sql`,
run the real code against it, and delete it afterwards. They cover the parts
where the behaviour is MySQL's rather than Python's — the backup merge and the
period export.

Everything at once:

```bash
cd analytics_api && ../.venv/bin/python -m pytest -m ""
```

### Requirement for the integration suite

A local MySQL **server** — the `mysqld` binary, not only the `mysql` client.

> Deployment runs **MySQL 8.0** (see `docker-compose.yml`). These tests require
> **8.0 or newer** and skip below it, because the schema in `db/` uses syntax
> older servers reject. Prefer 8.0.x: a newer server will pass, but it is
> answering as a different MySQL than the one in production.

| Platform | How to get it                                                                                    |
| -------- | ------------------------------------------------------------------------------------------------ |
| macOS    | `brew install mysql` — installs the server as well as the client                                 |
| Linux    | `sudo apt install mysql-server` (Debian/Ubuntu) or `sudo dnf install mysql-server` (RHEL/Fedora) |
| Windows  | [MySQL Installer](https://dev.mysql.com/downloads/installer/) — choose the **Server** component  |

Verify with: `mysqld --version`

You do not need to start it, configure it, or create a database. The test session
starts its own instance on a free port with its own data directory under your
temp folder, and removes both when it finishes. A MySQL you already run is never
contacted, and no deployment is reachable from the tests.

When `mysqld` is missing the integration tests **skip** rather than fail, so a
checkout without MySQL still reports green.

---

## Adding a test

Put it in the fast suite unless the behaviour under test is the database's. If it
is, mark the module and take the fixture:

```python
import pytest

pytestmark = pytest.mark.integration


def test_something(clean_databases):
    clean_databases.run(
        "INSERT INTO accelerometer (timestamp, device_id) VALUES (100, 'phone-a')",
        "aware_android",
    )
    ...
```

`clean_databases` truncates the study tables first, so each test starts from a
known state, and returns the server. Use `mysql_server.url(database)` when you
need a SQLAlchemy engine pointed at it.
