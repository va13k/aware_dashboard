# The Configurator

The page a researcher uses to describe a study: its title and contact details, which
sensors the phones record, how often, and which questions they ask. It is where a
researcher's answers enter the study model, and everything a phone eventually does
follows from a save made here. The deploy writes into the same model, but only the
facts about the machine it found: the host, the protocol, the generated credentials.
Nothing about the study's intent is decided anywhere but here.

A Django backend and a React front end, built into one container. It is forked from
[AWARE-Configurator](https://github.com/awareframework/AWARE-Configurator), whose own
document is kept as [`README.upstream.md`](README.upstream.md) and does not describe
this deployment.

Researchers reach it at `/configurator/`, behind the login, and the walkthrough of
the form is in the [main README](../README.md). This document is about the code in
this directory.

---

## What a save does

The form's shape is inherited: it submits one Android study configuration, the file
AWARE clients have always downloaded. That is not the shape the rest of the stack
needs, so a save is a round trip rather than a write.

```
form submits an Android config
        │
        ▼
update_source_from_android_config   maps the submitted fields onto the study model
        │
        ▼
source.json                         the model, updated under a lock
        │
        ▼
write_outputs                       four files, generated from the model
```

The model is the thing that persists. The four files below are generated from it and
can be regenerated at any time, which is why nothing reads a study's intent out of
them:

| Written | Read by |
| --- | --- |
| `studies/studyConfig.json` | Android phones, over nginx `/2/<key>` |
| `aware-micro-server/aware-config.json` | the iOS micro-server |
| `aware-micro-server/aware-config.android.json` | the Android micro-server, kept `0600` because it carries a server credential |
| `aware-micro-server/esm/ios-esm-config.json` | iOS phones, over nginx `/esm/` |

Two things happen before any of it is written. The dataflow is validated, and a
combination the deployment cannot honour is refused with a reason naming what is
missing, so a study is never left half-applied for two dataflows. And if the save
changes the ingest credentials, they are applied to MySQL inside the same locked
update: a database that rejects the change leaves `source.json` untouched, so the
served config is only regenerated once the new credentials are actually in effect.

The generated files reach a phone at different speeds. `studyConfig.json` is served
by nginx and is live as soon as it is written; the two micro-server configs are
re-read by the running instances within seconds. What a phone then does about it
depends on when it next checks in, which the [main
README](../README.md#how-a-change-reaches-a-participants-phone) describes.

---

## The endpoints

Six routes, in [`aware_light_config_Django/urls.py`](aware_light_config_Django/urls.py).
Everything else falls through to the React app's `index.html`, and all of it sits
behind `auth_request` in nginx, so every route here requires a researcher login.

Four of them are what the form uses:

| Route | What it is for |
| --- | --- |
| `GET /get_token/` | The CSRF cookie the form's POSTs need. |
| `GET /deployment_facts/` | What the study is running on, so the form can describe the deployment instead of guessing: the dataflow, the protocol, whether MySQL is reachable beyond this host, and which account the Android writes authenticate as. |
| `GET /get_participant_password/` | The ingest account's current password, so the field that changes it can also show it. |
| `POST /save_json_file/` | A submitted study configuration. This is the round trip above. |

Two are routed and implemented but called by nothing in this repository, neither by
the front end nor by setup:

| Route | What it does |
| --- | --- |
| `POST /test_connection/` | Reports whether a given MySQL host, database and account can be written to. |
| `POST /initialize_database/` | Connects with administrator credentials from the request body and applies [`db/android-tables.sql`](../db/android-tables.sql), then grants the study's own account what it needs. |

They date from the Configurator being the thing that set a study's database up.
Setting one up now belongs to [`setup/`](../setup/README.md), and
`init_study_tables.py` is what creates tables for both platforms. `db.py` still
reads the same generated schema the deployment uses, so the two cannot drift, but
nothing drives either route.

There is also a static route for `studies/files/`, which exists only so the
Configurator works when run on its own. In the full stack nginx serves that path and
the route is never reached.

---

## What the form reports rather than offers

The Android dataflow is shown and cannot be changed here. Two reasons, and either
one alone would be enough.

It re-addresses the study. A phone joined at an address the dataflow decides, so
switching it means every enrolled participant has to join again. And it is half a
deployment setting: the published database port follows from it, and only bringing
the deployment up again applies that, which a page inside a container cannot do.

The submitted value is therefore ignored rather than trusted. A browser holds its
own copy of the config that round-trips through the form, so accepting it would let
a stale tab re-address a running study. Changing the dataflow is done by running
setup again.

---

## The password field

It is the one field here that changes something outside the study model, and it
needs the login in front of it.

The account it changes is whichever one the study's dataflow puts on the ingest
path, and the field shows the password it also sets. It has to be handed over by its
own route because it cannot be read back from anywhere else: on the `direct` path
the served config redacts the password when the study asks for that, and the file is
public; on the `webservice` path the served config carries no database block at all.
Either way the field would load empty. The route lives under `/configurator/`, which
nginx gates behind the researcher login, so the password only ever reaches an
authenticated researcher.

---

## Working on it

Python 3.11 and Node 18, both pinned in the [`Dockerfile`](Dockerfile), which builds
the React app in one stage and serves it from gunicorn in the next. The front end is
built with `PUBLIC_URL=/configurator`, so the base path is baked in at image build
time and a change to it needs a rebuild.

```bash
python -m pytest AWARE-Configurator -q
```

Three modules: the mapping from a submitted config onto the study model, and the
participant-database helpers twice over, once with the connection mocked and once
against a real MySQL. The integration module skips itself unless a server is
listening on `127.0.0.1:3306`, so the suite is hermetic on a machine with no stack
running. Run from the repository root, because
[`aware_light_config_Django/settings.py`](aware_light_config_Django/settings.py)
resolves `PROJECT_ROOT` to the repository and imports `shared_config` from there.
They need no `.env`: `DJANGO_SECRET_KEY` is the only variable Django insists on, and
`conftest.py` supplies it.

For the front end:

```bash
cd AWARE-Configurator/reactapp && npx react-scripts test --watchAll=false
```

Both are CI jobs, `Configurator backend` and `Configurator frontend`, in
[`.github/workflows/check.yml`](../.github/workflows/check.yml).

The container mounts the repository at `/project`, which is how it reaches
`source.json` and `shared_config`, and writes the study files into `studies/`. To
pick up a backend change:

```bash
docker compose up --build -d configurator
```

`preparation.sh` and `util/nginx_config_*` are upstream's installer for a standalone
host. Nothing in this deployment calls them, and running `preparation.sh` on a host
serving this stack rewrites that host's nginx configuration.
