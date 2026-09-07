# Architecture

One Docker Compose project, eleven containers, one public port. This document is the
map: what runs, what each part is for, and how a request or a sensor row travels
through it. It describes the deployment as it stands; [the deploy
pipeline](deploy-pipeline.md) describes how it gets built.

For working inside a single component, its own README goes deeper:
[analytics_api](../../analytics_api/README.md),
[dashboard](../../dashboard/README.md).

---

## Two choices shape everything else

Almost every difference between two deployments of this stack comes from two
declared answers, and both live in the study model at [`source.json`](../../source.example.json).

| Choice | Field | Values | What it decides |
| --- | --- | --- | --- |
| **Android dataflow** | `deployment.dataflow.android` | `direct`, `webservice` | Whether an Android phone opens MySQL itself or posts to the Android micro-server |
| **Database placement** | `database.host` | an internal name, or a host the researcher gives | Whether this deployment runs its own MySQL container or connects to one it does not administer |

iOS is always `webservice`: the micro-server *is* the iOS path, and an iPhone has no
direct-database client. The reasoning behind each choice is written where it is
implemented, in [`shared_config/dataflow.py`](../../shared_config/dataflow.py) and
[`shared_config/placement.py`](../../shared_config/placement.py).

The placement is visible in the compose invocation. When the study names its own
database, the deploy writes `docker-compose.external-db.yml`, which removes the
`mysql` service and the `depends_on` of every service that waits on its health
check. The file's presence *is* the placement, which is why both entry scripts read
for it before they call `docker compose`.

---

## The containers

| Service | Container | Built from | Reachable at | Role |
| --- | --- | --- | --- | --- |
| `nginx` | `aware_nginx` | `nginx:alpine` | host `:80`, `:443` | The only public surface. Routes everything, terminates TLS, enforces both kinds of authentication |
| `dashboard` | `aware_dashboard` | [`./dashboard`](../../dashboard) | `:80` internal | React frontend a researcher browses collected data in |
| `dashboard-api` | `aware_dashboard_api` | [`./analytics_api`](../../analytics_api) | `:8000` internal | Reads for the dashboard, exports, backups, and the session check nginx calls |
| `counts-refresher` | `aware_counts_refresher` | [`./analytics_api`](../../analytics_api) | — | The same image on `app.refresh_counts`, keeping per-sensor row counts current so no page runs `COUNT(*)` on a live table |
| `configurator` | `aware_configurator` | [`./AWARE-Configurator`](../../AWARE-Configurator) | `:8000` internal | Django + React app a researcher configures the study in |
| `micro-server` | `aware_micro` | [`./aware-micro-server`](../../aware-micro-server) | `:8080` internal | iOS ingest: receives uploads and writes them to `aware_ios` |
| `micro-server-android` | `aware_micro_android` | [`./aware-micro-server`](../../aware-micro-server) | `:8082` internal | Android ingest on the webservice dataflow, and the enrolment gate |
| `mysql` | `aware_mysql` | `mysql:8.0` | `${MYSQL_BIND_ADDRESS:-127.0.0.1}:3306` | The study's two schemas. Present on the bundled placement only |
| `mysql-backup` | `aware_mysql_backup` | `mysql:8.0` | — | Scheduled dump of both schemas into `${MYSQL_BACKUP_HOST_DIR}` |
| `mqtt` | `aware_mqtt` | `eclipse-mosquitto:2` | `${MQTT_PUBLIC_PORT:-1883}` | Carries what a researcher sends to a phone: a sync request, a question, a notice |
| `setup-wizard` | `aware_setup` | [`./setup`](../../setup) | host `:9999` | The configuration form. Runs under the `setup` compose profile and is removed once the deploy reports healthy |

Two micro-server instances, one image. Android and iOS data live in different
schemas in a different row shape, so one instance cannot serve both: each gets its
own config file, its own study number and its own database account. The study number
is what the routes below are keyed on — iOS is `1`, Android is
[`dataflow.ANDROID_STUDY_NUMBER`](../../shared_config/dataflow.py), which is `2`.

---

## What nginx does with a request

Every public request arrives at nginx, and it sorts them into three kinds by *what
proves the caller may ask*.

**A researcher proves a session.** `auth_request /auth/validate` asks
`dashboard-api` before the request is proxied, and `error_page 401` sends an
unauthenticated caller to the login page.

| Route | Goes to | Notes |
| --- | --- | --- |
| `/dashboard/` | `dashboard:80` | |
| `/api/` | `dashboard-api:8000` | |
| `/api/live` | `dashboard-api:8000` | The live WebSocket. `auth_request` guards the handshake only, so [`routers/live.py`](../../analytics_api/app/routers/live.py) checks the session again itself; the location omits `error_page 401` deliberately, because a socket cannot render a login page |
| `/configurator/`, `/configurator/static/` | `configurator:8000` | |
| `/studies/`, `/studies/files/` | static, from `./studies` | `autoindex off`: a listing would name every file an earlier deployment left behind |
| `/setup-launch/`, `/backup/` | static pages | |
| `/auth/`, `/auth/validate` | `dashboard-api:8000` | The login form, and the internal subrequest every route above depends on |

**A phone proves the study key.** A participant's phone holds no session. The key it
presents in the path is compared against `$study_key`, which
[`nginx/study-key.conf`](../../nginx/http.conf) carries and the deploy writes;
without that file nginx refuses to start rather than serving the config unguarded.

| Route | Goes to | Notes |
| --- | --- | --- |
| `/2/<study_key>` | `./studies/studyConfig.json` | The Android study config, served as a file. On the direct dataflow it carries the database account the phone opens, which is why the key is compared rather than captured and dropped |
| `/studies/files/<study_key>/<file>` | `./studies/<file>` | The same files by key, which is how a phone on the direct dataflow reads its configuration |

**Everything else is a client endpoint the micro-servers answer.**

| Route | Goes to | Notes |
| --- | --- | --- |
| `/2/<a>/<b>/<c>` | `micro-server-android:8082` | Android upload, rewritten to the micro-server's `/index.php/2/...` |
| `/<n>/<key>` | `micro-server:8080` | iOS join and config fetch |
| `/<n>/<a>/<b>/<c>` | `micro-server:8080` | iOS table upload, rewritten the same way |
| `/index.php/` | `micro-server:8080` | The route AWARE clients have always posted to |
| `/cache/` | `micro-server:8080` | Cached assets: the QR image, sensor icons |
| `/android-qr.png` | `micro-server-android:8082/qr.png` | The Android study's QR code, rendered from the join link its own config declares. Public, because a joining participant reads it |
| `/esm/` | `./aware-micro-server/esm/` | The iOS ESM config |
| `/`, `/assets/` | static | The landing page |

`nginx/http.conf` and `nginx/https.conf` hold the same routes; the deploy mounts one
of them as `default.conf` according to `PROTOCOL`.

---

## Where a row comes from

Three ingest paths, and the dataflow picks which of the first two an Android study
runs.

**Android, `webservice`** — the phone posts, the server writes:

```
phone ──HTTPS──▶ nginx /2/… ──▶ micro-server-android ──▶ MySQL aware_android
                                        │
                                  EnrolmentGate: is this device
                                  enrolled in this study?
```

**Android, `direct`** — the phone opens the database itself:

```
phone ──MySQL──────────────────────────────────────────▶ MySQL aware_android
     └─HTTPS──▶ nginx /2/<key> ──▶ studyConfig.json (carries the db account)
```

**iOS** — always through the server:

```
iPhone ──HTTPS──▶ nginx /<n>/… ──▶ micro-server ──▶ MySQL aware_ios
```

And out again, the same for every path:

```
MySQL ◀── dashboard-api ◀── nginx /api/ ◀── dashboard   (browser)
      ◀── counts-refresher                              (row counts)
      ◀── mysql-backup                                  (scheduled dump)
```

A phone collects into its own storage and uploads on the cadence the study config
declares: `frequency_webservice` for the data, `frequency_sync_config` for the config
it re-reads, with `webservice_wifi_only` and `webservice_charging` deciding what an
upload waits for. The client's own scheduler holds that cadence, so the phone arrives
on its own and each upload resumes from the last row id it sent. A researcher can ask
for one now, over the broker, when a phone has gone quiet.

---

## The database

Two schemas hold the study: `aware_android` and `aware_ios`, one per platform,
because the clients write different row shapes. Beside the sensor tables each schema
carries a set the deployment maintains itself, derived from the study data rather
than mixed into it. One copy lives in each platform schema, so a refresh reads and
writes within a single connection.

| Table | Written by | Holds |
| --- | --- | --- |
| `record_counts` | `aware_analytics` | Exact per-sensor, per-device row counts, refreshed from an `_id` watermark off the request path |
| `coverage_hourly` | `aware_analytics` | How much arrived per hour, keyed by table |
| `device_enrolment` | `aware_analytics` | A device's standing in the study, derived from its event log |
| `device_exclusions` | `aware_analytics` | Devices a researcher took out of the study |
| `messages_sent` | `aware_analytics` | What was sent to a phone, and when |
| `device_contacts` | the platform's ingest account | When a device last reached the server |
| `refusals` | the platform's ingest account | What the enrolment gate turned away, and how often |

The whole schema is one file, [`db/init_all.sql`](../../db/init_all.sql), which MySQL
applies through `--init-file` on every start. It is a build product: MySQL reads the
init file server-side and cannot `SOURCE` another, so
[`db/build_init_all.py`](../../db/build_init_all.py) concatenates the three
hand-written sources into it and can check the result against the Android client's
own declared tables.

Every account is narrow, and the list is derived in one place,
[`database.profiles()`](../../shared_config/database.py):

| Account | Holds | For |
| --- | --- | --- |
| `aware_android_participant` | `INSERT` on `aware_android` | A phone on the direct dataflow |
| `aware_android_server` | `INSERT` on `aware_android`, plus the enrolment registry, refusal counters and device-metadata rows the gate keeps | The Android micro-server |
| `aware_ios_participant` | `INSERT` on `aware_ios` | The iOS micro-server — a server's credential, despite the name |
| `aware_analytics` | `SELECT` on both schemas, and write on the derived tables listed below | `dashboard-api`, `counts-refresher` |
| `aware_backup` | `ALL PRIVILEGES` on the two schemas, nothing global | Dump and restore from the dashboard |

Both Android accounts exist whichever dataflow the study runs, so a study that
switches paths finds its new account already holding the password its generated
configuration names.

On the bundled placement the connection is encrypted and there is no setting to turn
it off: MySQL generates its own certificate on first start, and every account is
created `REQUIRE SSL`. On a database the researcher names, encryption is a property
of somebody else's server, so it is declared, checked before the study deploys, and
refusable.

---

## The generated files, and who reads them

Nothing in this table is committed. Each is written by
[`setup/deploy_config.py`](../../setup/deploy_config.py) from `.env` and
`source.json`, and mounted into whichever container needs it.

| File | Read by |
| --- | --- |
| `.env` | Compose, for every service's environment |
| `source.json` | The deploy, the Configurator, the API — the study model itself |
| `studies/studyConfig.json` | Android phones, through nginx; the API, to diff against what a device carries |
| `studies/index.html` | The studies landing page |
| `aware-micro-server/aware-config.json` | `micro-server`, and the API for the config diff |
| `aware-micro-server/aware-config.android.json` | `micro-server-android` |
| `aware-micro-server/esm/ios-esm-config.json` | iOS clients, through nginx `/esm/` |
| `nginx/study-key.conf` | nginx, as the key it compares a phone's request against |
| `nginx/auth/.htpasswd` | nginx |
| `mosquitto/mosquitto.conf`, `passwords`, `acl` | `mqtt` — who may publish, who may only receive |
| `docker-compose.external-db.yml` | Both entry scripts, as the placement |
| `deployment-urls.json` | The entry scripts, to print the access links |
| `copy-study-data.sh` | The researcher, when a placement switch is asked to carry the collected rows |

---

## Where to read next

| To understand | Read |
| --- | --- |
| How a deployment is built, step by step | [deploy-pipeline.md](deploy-pipeline.md) |
| The read layer, its endpoints and its tests | [analytics_api/README.md](../../analytics_api/README.md) |
| The dashboard's pages and live channel | [dashboard/README.md](../../dashboard/README.md) |
| The study model and the two platform configs | [`shared_config/serializers.py`](../../shared_config/serializers.py) |
| Deploying it as a researcher | [the root README](../../README.md) |
