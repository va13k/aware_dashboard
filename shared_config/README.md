# Shared config

The study model, and everything derived from it. One study is declared once — in
`source.json` — and this package turns that declaration into the two platform
configs the phones read, the accounts the database holds, the addresses each
service connects on, and the answers the deploy is checked against.

It is a plain Python package, standard library only outside its tests. It is imported by
the deploy scripts on the host, and mounted read-only into the `dashboard-api`
container at `/app/shared_config`; the Configurator reaches it through the project
mount. This document is for working on the package itself — for the deployment it
serves, see [docs/dev/architecture.md](../docs/dev/architecture.md).

---

## Why it exists

Four readers need the same answers about one study, and they run in different
places: the deploy on the host, the Configurator in its container, the API in
another, and the checks that ask the database what it will be asked at runtime.

The answers are not restatements of a field. *Which account is on the ingest path*
follows from the dataflow. *Which address a service connects on* follows from the
placement. *Whether the published config carries database coordinates at all*
follows from both. Derived separately by each reader, they drift — and the failure
that drift produces is the quiet kind: a study that deploys, comes up healthy, and
collects nothing, or collects into a schema the dashboard is not reading.

So each answer is derived once, here, and every reader asks the same function.

```
source.json  ──▶  shared_config  ──▶  setup/deploy_config.py   → the generated files
(the study)            │               setup/init_study_tables.py → schemas, accounts
                       │               setup/verify_*.py         → the checks
                       ├──────────────▶ analytics_api            → backup, messaging
                       └──────────────▶ AWARE-Configurator       → what a researcher edits
```

---

## The study model

`source.json` is this deployment's own file: it holds participant credentials and
database passwords, so it is gitignored and materialized from the committed
[`source.example.json`](../source.example.json) on first use. Its top level:

| Block | Holds |
| --- | --- |
| `version` | The model's own schema version |
| `study` | Id, title, description, whether it is active, when it started |
| `researcher` | Name and contact, as published to participants |
| `deployment` | Public host, port, protocol, and `dataflow` per platform |
| `database` | The one declared `host`, the TLS declaration, and each platform's schema, port and account |
| `android` | The Android client's own settings block — one flat map of every sensor toggle and frequency |
| `ios` | The iOS client's study number, key, server block, sensors, plugins and plugin settings |
| `shared` | The settings that mean the same thing on both platforms, and the ESMs |

---

## The modules

| Module | Answers |
| --- | --- |
[`dataflow.py`](dataflow.py) | Where a platform's data goes. `direct` — the phone opens MySQL itself; `webservice` — it posts to the micro-server. Declared per platform in `deployment.dataflow`; iOS is `webservice` and can be nothing else |
[`placement.py`](placement.py) | Where the database runs. `bundled` — a container this deployment administers; `external` — a host the researcher names. Read from `database.host` rather than stored separately, so two fields cannot disagree about which database a study uses |
[`database.py`](database.py) | One declared host resolved into the address each reader can use, and two answers settled in one place: [`profiles()`](database.py), every account this deployment opens the study's database with, and [`admin_credentials()`](database.py), the account it administers that database as |
[`serializers.py`](serializers.py) | The study model turned into the Android config, the Android micro-server config, the iOS config and the iOS ESM file. The largest module, and the one where a field is silently lost |
[`source_store.py`](source_store.py) | Reading and writing `source.json` under an advisory file lock, so the Configurator saving and a deploy reading do not interleave |
[`runtime.py`](runtime.py) | Atomic writes with an explicit permission mode, `.env` reading and writing, and the public base URL every generated address is built from |
[`messaging.py`](messaging.py) | The broker: the topics the client already subscribes to, the two accounts, the ACL, and the per-device rate limits |
[`mysql_client.py`](mysql_client.py) | How setup issues SQL before anything else works — through the bundled container, or through a throwaway client container on the compose network for a database the researcher named |
[`certificates.py`](certificates.py) | Reading a certificate out of whatever it arrived wrapped in, so the Configurator accepting one and the deploy publishing it agree exactly |

---

## Two rules worth knowing before changing anything

### A sensor field has to be wired through every layer

Adding one setting to the Android config touches four places, and a field missing
from any of them is dropped without an error:

```
reactapp/src/pages/Upload.jsx      load it into its Recoil atom
reactapp/src/pages/SensorData.jsx  show and edit it
reactapp/src/pages/Overview.jsx    write it into the sensors[] array it POSTs
reactapp/public/study-config.json  carry it in the template
```

If it also belongs on iOS, add it to `COMMON_SHARED_SENSOR_FIELDS` here. The iOS
settings are built in three passes, and the last one wins:

1. `ios.sensors` as the baseline — this is where iOS-only sensors live
   (`IOS_ONLY_SENSOR_NAMES`: `significant_motion`, `websocket`, `mqtt`)
2. `android.settings` as an override
3. `build_shared_sensor_settings`, from `COMMON_SHARED_SENSOR_FIELDS` — highest

An iOS-only sensor added to `COMMON_SHARED_SENSOR_FIELDS` gets an Android answer
written over its iOS one, so those two lists stay disjoint.

### One value, one generator

Every secret has exactly one place that mints it, and a blank means "not yet
minted". `setup/deploy_config.py` reads a blank and generates; a rotation empties
the value rather than replacing it, so it takes the same path a first deploy does.
Nothing here generates a second time on top of a value that already exists — a
study whose key changes on every redeploy collects nothing, because the key is in
the address the phones were given.

---

## Conventions worth knowing early

- **Every generated file states its mode.** `atomic_write_text` takes
  `SHARED_MODE` (`0644`, for anything nginx or a container's own user reads) or
  `SECRET_MODE` (`0600`). The default is the secret one. Left implicit, a file's
  permissions end up decided by whichever writer ran last, which breaks readers
  running as another user without saying so.
- **`source.json` is read and written under a lock.** Use `read_source`,
  `write_source` and `update_source` rather than touching the path.
- **A choice nothing recognises stops the run** where the researcher gave it.
  `dataflow.validate` and `placement.validate` refuse at the wizard boundary
  rather than letting a default be substituted downstream — a study quietly
  collecting the wrong way is the failure that appears weeks later in the
  coverage grid.
- **Both Android accounts exist whichever dataflow runs**, so a study that
  switches paths finds its new account already holding the password its generated
  configuration names.
- **Reasoning lives in the module docstrings.** Each one explains what the module
  decides and why the decision is made there; they are the fastest way in.

---

## Running the tests

From the repository root:

```bash
.venv/bin/python -m pytest shared_config -q
```

They need nothing running: no Docker, no database, no network.

Each module here has a test file beside it, and so do the scripts in `setup/` and
`db/`: this is where the suite covering the deployment lives, so a test file named
for something outside this package is testing that thing from here. `pytest
shared_config` runs all of it, which is what the CI job does.
