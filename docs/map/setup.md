# setup

Everything that turns a checkout into a running study: the wizard a researcher fills
in, the deploy that writes every generated file, and the checks that say whether it
worked. Prose: [`setup/README.md`](../../setup/README.md).

The order the deploy runs in is
[deploy-pipeline.md](../dev/deploy-pipeline.md). This note is where each step lives.

Entry is `setup.sh` or `setup.bat` at the repository root. Both must stay in step:
a change to one is a change to the other, and
`shared_config/test_setup_entrypoints.py` holds them together.

---

## What owns what

| Concept | File |
| --- | --- |
| Writing every generated file from the model and `.env` | [`deploy_config.py`](../../setup/deploy_config.py) |
| Creating the study tables, both platforms | [`init_study_tables.py`](../../setup/init_study_tables.py) |
| Whether the ports the study needs are free | [`check_ports.py`](../../setup/check_ports.py) |
| The address participants will reach | [`detect_public_host.py`](../../setup/detect_public_host.py) |
| Publishing the bundled certificate authority to phones | [`publish_authority.py`](../../setup/publish_authority.py) |
| Whether the database is reachable and shaped right | [`verify_database.py`](../../setup/verify_database.py) |
| Whether a row can actually be written and read back | [`verify_ingest.py`](../../setup/verify_ingest.py) |
| Sending a message to a participant's phone | [`send_message.py`](../../setup/send_message.py) |
| The studies landing page | [`studies_index_template.html`](../../setup/studies_index_template.html) |
| The nightly database dump, in its own container | [`mysql-backup/backup.sh`](../../setup/mysql-backup/backup.sh) |

### The wizard

A container of its own, under the `setup` compose profile, built from
[`Dockerfile`](../../setup/Dockerfile).

| Concept | File |
| --- | --- |
| The server, and which services it waits for | [`server.py`](../../setup/server.py) |
| The form | [`setup.html`](../../setup/setup.html), [`script.js`](../../setup/script.js), [`style.css`](../../setup/style.css) |
| The endpoint the form posts to | [`deploy.sh`](../../setup/deploy.sh) |
| Turning the submitted answers into `.env` | [`write_request_env.py`](../../setup/write_request_env.py) |
| The credentials and links it answers with | [`deploy_response.py`](../../setup/deploy_response.py) |

---

## What changes together

- **A new question in the form** needs the field in `setup.html`, its handling in
  `write_request_env.py`, and a default in `env.example`. A value the form collects
  and `write_request_env.py` does not clean never reaches `.env`.
- **A new service the wizard waits for** goes in the frozensets in `server.py`,
  which `shared_config/test_documented_counts.py` counts against the README.
- **The deploy writes into `source.json`**, not only out of it: the host, the
  protocol and the generated credentials are facts about the machine. Study intent
  is the Configurator's. See [shared_config](shared-config.md).
- **`verify_ingest.py` writes**, unlike the database check, which only reports. It
  inserts a probe row and reads it back.

---

## Traps

- **Windows has no `fcntl`, no `openssl` binary, and no `os.fchmod`.** Anything here
  that locks, hashes a password, or sets a mode has to work without them, because
  these scripts run on the host rather than in a container.
- **A file open on Windows cannot be deleted.** An atomic write closes the
  descriptor before unlinking the temporary file.

---

## Tests

```bash
python3 -m pytest shared_config -q
```

The suite covering these scripts lives in `shared_config`, alongside the model they
read. The deployment itself is exercised by the smoke test in CI, described in
[checks.md](../dev/checks.md#the-deployment-smoke-test).
