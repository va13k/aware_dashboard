# Setup

Everything that turns a checked-out repository into a running study. The wizard a
researcher fills in, the generator that writes every configuration file from what
they said, the script that creates the schema and the accounts, and the two checks
that ask the deployment the questions a phone will ask.

These scripts use only the Python standard library, so nothing has to be installed
on the host beyond Python 3 and Docker. They read the study model through
[`shared_config`](../shared_config/README.md), which is where the answers about one
study live.

**This document is about the files.** For the order they run in and what each step
decides, read [docs/dev/deploy-pipeline.md](../docs/dev/deploy-pipeline.md) — the
two are meant to be read together and neither repeats the other.

---

## Where these run

Two places, and it matters for every path in the code.

**On the host**, invoked by `setup.sh` or `setup.bat`. `PROJECT` resolves to the
repository root, and `docker` is reached through whatever prefix the entry script
passes.

**Inside the wizard container**, `aware_setup`, built from the
[Dockerfile](Dockerfile) here. `/project` is the bind-mounted repository, and the
Docker socket is mounted read-only so the wizard can poll service health and put a
MySQL client on the deployment's network. Each script resolves this itself:

```python
PROJECT = pathlib.Path("/project")
if not PROJECT.exists():
    PROJECT = SCRIPT_DIR.parent
```

The wizard's process runs as root, since it has to read the socket, so
`deploy_config.chown_generated_paths` hands the files it wrote back to the user who
deployed, and refuses when the target does not match the project directory's own
owner.

Which user that is comes from `deploy_config.ensure_host_identity`. `setup.sh` writes
`HOST_UID`/`HOST_GID` from the deploying user's own ids, and where there is no `id -u`
to ask, the identity is taken from the owner of the project directory as the
containers see it: the deploying user on Linux, and root on Docker Desktop, which is
the only user that can write into the directories the deploy creates in the mount.

---

## The files

### The wizard

| File | Is |
| --- | --- |
[`server.py`](server.py) | The HTTP server on port 9999. Mints a URL-safe token at start, serves everything under `/<token>/`, and writes that path to `.wizard_url` for the entry script to print. Also answers `/status` with container health, `/check-database`, and `/database.sql` |
[`setup.html`](setup.html), [`script.js`](script.js), [`style.css`](style.css) | The form. Copied into the image as `index.html` and its two assets |
[`deploy.sh`](deploy.sh) | The CGI endpoint behind `/cgi-bin/deploy`. `GET` returns what `.env` already holds; `POST` validates the body, runs the generator, and touches `.env.saved` — the marker the entry script waits on |
[`write_request_env.py`](write_request_env.py) | Validates a wizard save against a fixed key allowlist and writes `/tmp/aware-dashboard-request.env`. A blank field is left out rather than written empty, so an existing value survives; a connection string pasted into the host field is taken apart into its parts |
[`deploy_response.py`](deploy_response.py) | The JSON the page reads after a successful save: the researcher's credentials and the deployment's access links |
[`detect_public_host.py`](detect_public_host.py) | Scores the machine's network interfaces and picks the address to suggest, skipping loopback, Docker bridges and VPN adapters. Has its own paths for WSL and Windows |

### The deploy

| File | Is |
| --- | --- |
[`deploy_config.py`](deploy_config.py) | The generator. Reads `.env`, the wizard's request and `source.json`; writes every generated file. The longest file here by far, and the one to read first — its `main()` is the whole pipeline in order |
[`init_study_tables.py`](init_study_tables.py) | The only thing that creates anything: both schemas, every account with the password this study holds, and the table definitions. Runs on both placements and on every deploy, which is what keeps `.env` and the database from drifting |
[`publish_authority.py`](publish_authority.py) | Publishes the certificate authority a bundled database generated on first start, once the stack is up. Guarded, so a deployment that has already published one does nothing |
[`check_ports.py`](check_ports.py) | The addresses this deployment publishes, asked about before the containers that need them are built. Reads `.env` for the broker's and the database's; asks a publish on every interface at each address this machine claims as its own, so a server bound to one of them is found; and treats a port held by an `aware_*` container as available — that is a redeploy, not a conflict |
[`studies_index_template.html`](studies_index_template.html) | The participant-facing join page, rendered into `studies/index.html` with this study's links, QR code and per-platform install instructions |

### The checks

Neither writes to the study, and neither stops a run: the stack is up either way,
and the wizard shows the same result in the browser.

| File | Asks |
| --- | --- |
[`verify_database.py`](verify_database.py) | Five questions of the database — reachable, encrypted as declared, both schemas present, every account authenticating, the tables there. Also renders the SQL to hand to an administrator when setup may not create anything itself |
[`verify_ingest.py`](verify_ingest.py) | The question a phone asks: the endpoint at its public address, the certificate that address presents, and a row posted the way a client posts one — then found in the database and taken back out. Walks whichever dataflow the study runs |

### Running alongside

| File | Is |
| --- | --- |
[`send_message.py`](send_message.py) | Reaching a phone from the command line: ask it to sync, ask it for a config update, ask the participant a question, tell them something, or read what a device reported receiving |
[`mysql-backup/backup.sh`](mysql-backup/backup.sh) | The scheduled dump, run by the `mysql-backup` container. Skips the dashboard's own cache tables, since each summarises the row ids of the deployment that built it |

---

## Conventions worth knowing early

- **`--docker-prefix` is how a script reaches Docker.** Every script that shells
  out to `docker` accepts it, repeatably. `setup.sh` passes `--docker-prefix sudo`;
  `setup.bat` passes nothing, because Docker Desktop needs no prefix. A script that
  needs Docker and does not take this flag is a bug waiting for the other platform.
- **A wizard save cannot set an arbitrary variable.** `write_request_env.py`
  validates against a fixed key allowlist and writes only what it recognised, so
  the HTTP body reaches `.env` through a known set of fields and no other path.
- **The generated files state their permissions.** Writing goes through
  `shared_config.runtime.atomic_write_text` with `SHARED_MODE` or `SECRET_MODE`,
  never `write_text`, so a file's mode is decided by who has to read it rather than
  by whichever writer ran last.
- **What is written is read back.** `deploy_config` finishes by re-reading the
  files it produced and checking the dataflow and the placement in them, because
  those files are what a phone will be served.
- **The checks report, they never create.** A check that created what it was asked
  about could only report success — and against a database the researcher has not
  agreed to have changed yet. What is missing before a first deploy is a line
  saying which side will create it.
- **A refusal comes early.** `apply_dataflow` and `apply_placement` run before
  anything is generated, so an incoherent combination leaves no half-written study.
- **Both entry scripts are the same deployment.** `setup.sh` and `setup.bat` must
  name the same helpers and wait on the same containers;
  [`shared_config/test_setup_entrypoints.py`](../shared_config/test_setup_entrypoints.py)
  holds them to it.

---

## Running things by hand

From the repository root. On macOS and Linux add `--docker-prefix sudo`; on Windows
leave it off.

```bash
python3 setup/verify_database.py --docker-prefix sudo
python3 setup/verify_ingest.py --docker-prefix sudo
python3 setup/init_study_tables.py --docker-prefix sudo
python3 setup/deploy_config.py --docker-prefix sudo
python3 setup/detect_public_host.py
python3 setup/check_ports.py --docker-prefix sudo
python3 setup/send_message.py --docker-prefix sudo devices
```

`deploy_config.py` regenerates every configuration file from the current `.env` and
`source.json`. It is safe to re-run and is what the redeploy path calls, but it
rewrites files the running services have already read — so bring the stack up
afterwards rather than leaving it mid-change.

To mint a credential again, name it in `.env` and redeploy. The request is read
from the file rather than from the process environment, because that is where the
wizard writes it too:

```bash
echo "ROTATE=study-key" >> .env
```

Then run `./setup.sh` and choose *Deploy with current config*. `study-key` and
`broker` are the two rotatable names, and the request is cleared once acted on, so
a rotation happens on the deploy that asked for it. Both credentials live on phones
in the field: a new study key changes the address a phone uploads to, so every
participant rejoins by scanning the QR code again, and a new broker password stops
prompts reaching a phone until it has read its configuration.

---

## Running the tests

The suite covering these scripts lives beside the study model, because that is what
they read:

```bash
.venv/bin/python -m pytest shared_config -q
```

`test_verify_database.py`, `test_verify_ingest.py`, `test_bundled_admin.py` and
`test_setup_entrypoints.py` are the ones about this directory. They need nothing
running — the database is answered from a script and the entry scripts are read as
text.
