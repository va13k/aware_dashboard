# The deploy pipeline

What happens between `./setup.sh` and a study a phone can join. Every step below is
a script in [`setup/`](../../setup) that a researcher never has to run by hand, and
they run in this order for a reason: a refusal early means no half-written study.

The stack those scripts produce is described in [architecture.md](architecture.md).

---

## Two entry scripts, one deployment

| Script | For | Runs docker as |
| --- | --- | --- |
| [`setup.sh`](../../setup.sh) | macOS, Linux | `sudo docker`, and passes `--docker-prefix sudo` to every helper |
| [`setup.bat`](../../setup.bat) | Windows | `docker`, since Docker Desktop needs no prefix |

They are the same deployment written twice, so they are held to each other by
[`shared_config/test_setup_entrypoints.py`](../../shared_config/test_setup_entrypoints.py):
every `setup/*.py` either one names must exist, both must name the same set, and both
must wait on the same containers. Drift between them is a platform that stops half
way through with a stack of empty schemas behind it, which is exactly what that test
exists to catch.

Each script first checks that Docker, Compose v2 and Python 3 are on `PATH`, and
stops with an instruction rather than a traceback when one is missing. No other
runtime is needed on the host: everything else is built inside Docker, and the
helpers use only the Python standard library.

---

## Which path a run takes

```
                    .env AND aware-micro-server/aware-config.json present?
                                  │
                 ┌────────────────┴────────────────┐
                yes                                no
                 │                                  │
      "1) Deploy with current config"         the wizard
      "2) Edit configuration first"                 │
                 │            └────────────────────┐│
        deploy_stack                            wizard flow
```

**`deploy_stack`** regenerates every configuration file from what `.env` and
`source.json` already say, brings the stack up, and re-applies the study's database
accounts. It is the redeploy path, and the one to use after editing `.env` by hand —
`docker compose up` on its own leaves the existing database untouched, so its
accounts keep their old passwords.

**The wizard flow** asks for the configuration in a browser first, and the deploy is
run from inside the wizard as the researcher saves.

---

## The wizard

`compose --profile setup up -d setup-wizard` starts one container, `aware_setup`,
which mounts the project at `/project` and the Docker socket read-only.

[`setup/server.py`](../../setup/server.py) mints a URL-safe token at start, serves
everything under `/<token>/` and writes that path to `setup/.wizard_url`. The entry
script polls for that file, prints `http://<detected-host>:9999/<token>/`, and tries
to open a browser. The address comes from
[`detect_public_host.py`](../../setup/detect_public_host.py), which scores the
machine's interfaces and skips loopback, Docker bridges and VPN adapters.

The token is the only thing guarding the page, and the page holds this deployment's
database password and the researcher's own over plain HTTP. Both scripts say so
where they print it, and offer `SETUP_BIND=127.0.0.1` in `.env` plus an SSH tunnel
for a network the researcher does not trust.

| Route under `/<token>/` | Does |
| --- | --- |
| `/` , `/script.js`, `/style.css` | The form, from [`setup.html`](../../setup/setup.html) |
| `GET /cgi-bin/deploy` | Loads what `.env` already holds, so reopening the wizard shows the study that is running |
| `POST /cgi-bin/deploy` | Saves and deploys — the sequence below |
| `POST /check-database` | Runs `verify_database.py --quiet` against the fields as typed, so an unreachable database is a field to correct rather than a deployment that stops half way |
| `GET /database.sql` | The statements to create the schema and accounts by hand, for an institutional server setup may not touch |
| `GET /status` | Container health, which the page polls to know when to redirect |

A save is three steps in [`setup/deploy.sh`](../../setup/deploy.sh):

1. The request body goes to
   [`write_request_env.py`](../../setup/write_request_env.py), which validates every
   field against a fixed allowlist and writes `/tmp/aware-dashboard-request.env`. A
   field the researcher left blank is left out rather than written empty, so an
   existing value survives.
2. [`deploy_config.py`](../../setup/deploy_config.py) runs, generating everything.
3. `/project/.env.saved` is touched, which is the marker the entry script is waiting
   on. It then brings the stack up itself.

---

## `deploy_config.py` — two inputs, every generated file

The longest script in `setup/`, and the one worth reading first. It takes

- **`.env`** — this deployment's secrets and public address,
- **`/tmp/aware-dashboard-request.env`** — what the researcher just typed, when a
  wizard save is what invoked it,
- **`source.json`** — the study model, created from
  [`source.example.json`](../../source.example.json) when absent,

and produces every file in the generated-files table in
[architecture.md](architecture.md#the-generated-files-and-who-reads-them). In order:

| Step | What it does |
| --- | --- |
| `load_merged_env` | `.env` overlaid with the request, so a save wins over what stands |
| `apply_rotation_request` | Empties the credentials this deploy was asked to mint again — `ROTATE=study-key` or `ROTATE=broker`. Emptied rather than replaced, so each value keeps exactly one generator, and the request itself is cleared so a rotation happens once |
| `ensure_*` × 11 | Mints anything absent: the Django secret, the session secret, the study key and id, the researcher's credentials, and one password per database and broker account |
| `generate_htpasswd`, `persist_env` | Writes what nginx compares against, then `.env` |
| `seed_source_secrets` | Fills this deployment's generated credentials into the study model |
| `apply_dataflow` | Applies `deployment.dataflow` and settles the MySQL bind address with it. First, because a refusal here means nothing has been written yet |
| `apply_placement` | Applies where the database runs, and writes or removes `docker-compose.external-db.yml`. After the dataflow, because the *combination* is what can be refused |
| `apply_data_copy` | Writes `copy-study-data.sh` when a placement switch was asked to carry the rows already collected |
| `ensure_database_authority` | Reads the certificate authority out of the bundled database when it has generated one |
| `apply_broker` | The Mosquitto config, its accounts and its ACL |
| `write_android_config` | `studies/studyConfig.json` — what an Android phone fetches |
| `write_android_micro_config` | `aware-config.android.json`, written on either dataflow so a switch is a restart rather than a redeploy |
| `write_micro_config`, `write_ios_esm_config` | The iOS instance's config and ESM file |
| `write_studies_index`, `write_deployment_urls` | The studies landing page, and the links the entry script prints |
| `write_nginx_study_key` | `nginx/study-key.conf`. Without it nginx refuses to start rather than serving a study config unguarded |
| `check_dataflow_applied`, `check_placement_applied` | Reads the written files back, because a check is worth only as much as the files it inspects — and those are the files a phone will be served |
| `chown_generated_paths`, `check_config_permissions` | Aligns ownership with the deploying user, so the Configurator can write what it is meant to |

It prints a summary of what it decided: the dataflow per platform, where the
database is and how the connection is verified, whether backups follow a placement
switch, the broker's port and transport, and any rotation performed.

---

## `init_study_tables.py` — the only thing that creates

Run after `compose up`, and it is the single place anything is created. A bundled
database gets its whole schema from `db/init_all.sql`, which MySQL applies through
`--init-file` on every start; a database the researcher names has no such file, so
the script waits for MySQL, creates both schemas, creates every account with the
password this study holds, and applies the table definitions.

It runs on both placements and on every deploy, which is what keeps `.env` and the
database from drifting: a password edited in `.env` is re-applied to its account
here.

---

## `publish_authority.py` — the certificate a phone checks

A bundled database generates the authority it signs its own certificate with when
MySQL first starts, and that start follows the deploy which wrote the study. So
[`publish_authority.py`](../../setup/publish_authority.py) runs once the stack is up:
when the study is on the bundled database and the served config carries no authority
yet, it re-runs `deploy_config.py` so the file the phones fetch carries one. Both
entry scripts call it, so the question is asked once for one deployment.

---

## The two checks

Neither writes anything to the study, and neither stops the run — the stack is up
either way, and the wizard shows the same result in the browser.

**[`verify_database.py`](../../setup/verify_database.py)** asks the database what the
deployment will ask it: that the address answers and the credential authenticates,
that the connection is encrypted as the study declared and the authority verifies,
that both schemas exist, that every account connects with the password this study
holds, and that the tables a phone's rows land in are there. What is missing before
a first deploy is not a failure but a line saying which side is going to create it —
setup, or whoever administers a database setup may not touch.

**[`verify_ingest.py`](../../setup/verify_ingest.py)** asks the question a
participant's phone will ask, before anyone enrols: the ingest endpoint at its
public address, the certificate that address presents checked against the system
trust store, and a row posted the way the client posts one — admitted, found in the
study database, and taken back out again. Both dataflows are walked, because the
choice decides what a phone has to reach. The probe device is synthetic, named per
run, and everything keyed on that name is cleaned up whatever the outcome.

---

## Readiness, and the wizard's exit

`wait_for_service_redirect` polls `docker inspect` until every service in the
placement's list reports `healthy` or `running`, for up to six minutes. The bundled
database is in that list only when this deployment runs one.

On success the browser is redirected, the ingest check runs, and the wizard
container and `setup/.wizard_url` are both removed — the token goes with the server
that honoured it. When readiness is not reached the wizard stays up, because it is
where the self-test result is read.

The entry script then prints the access links from `deployment-urls.json`.

---

## What is still manual

Everything the deployment can decide for itself, it does. What remains needs a
person, and each is prompted for rather than assumed:

| Manual step | Why it stays manual |
| --- | --- |
| Installing Docker and Python 3 | A package manager and, on Windows and macOS, a GUI installer and a restart |
| Obtaining a TLS certificate | Domain ownership has to be proved to a certificate authority. The wizard takes the paths to a certificate already obtained |
| Opening ports 80 and 443 | Belongs to the host's firewall or the provider's console |
| Creating an external database, and allowing this machine to reach it | The provider's console, and an administrator account this deployment is given rather than creates |
| Running `database.sql` by hand | For an institutional server where the account given may insert and nothing else |
| Running `copy-study-data.sh` | It moves collected rows between two servers, so it is written out to run rather than done behind a browser |
| A participant syncing their phone | Both platforms store rows locally and upload on the participant's action |
