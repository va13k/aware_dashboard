# Configurator: the back end

Django, Python 3.11. It answers the form, maps what the form submits onto the study
model, and regenerates the platform configs.
Prose: [`AWARE-Configurator/README.md`](../../AWARE-Configurator/README.md).

It imports `shared_config` from the repository root, which the container reaches
through a mount at `/project`. See [shared_config](shared-config.md).

---

## What owns what

| Concept | File |
| --- | --- |
| Every route | [`aware_light_config_Django/urls.py`](../../AWARE-Configurator/aware_light_config_Django/urls.py) |
| Settings, and resolving `PROJECT_ROOT` | [`aware_light_config_Django/settings.py`](../../AWARE-Configurator/aware_light_config_Django/settings.py) |
| The form's endpoints, and the whole save path | [`App01/general.py`](../../AWARE-Configurator/App01/general.py) |
| Changing a MySQL account's password | [`App01/participant_db.py`](../../AWARE-Configurator/App01/participant_db.py) |
| Connecting, checking privileges, applying the schema | [`App01/db.py`](../../AWARE-Configurator/App01/db.py) |
| Two routes nothing calls | [`App01/database_operations.py`](../../AWARE-Configurator/App01/database_operations.py) |
| Supplying a secret key so the tests can import Django | [`conftest.py`](../../AWARE-Configurator/conftest.py) |

---

## The save path

One function chain in `general.py`, and it is the thing to read first:

`save_json_file` → `save` → `update_source(_merge_and_sync_credentials)` →
`update_source_from_android_config` → `write_outputs`.

`update_source_from_android_config` maps the submitted Android config onto the study
model. `write_outputs` generates the four files from the model. Everything between
happens inside the lock, so a credential MySQL rejects leaves `source.json`
untouched and no config is regenerated.

`write_outputs` refuses a dataflow the deployment cannot honour before writing
anything, and the reason names the piece that is missing.

---

## What changes together

- **A field the form gains** has to be mapped in `update_source_from_android_config`
  or it reaches `source.json` as nothing. See
  [configurator-frontend](configurator-frontend.md) for the four front-end layers it
  crosses first.
- **The generated files are products.** Editing
  `aware-micro-server/aware-config.json` by hand loses the edit at the next save or
  deploy.
- **The dataflow the form submits is ignored on purpose.** A browser holds its own
  copy of the config, and accepting it would let a stale tab re-address a running
  study.

---

## Traps

- **`test_connection/` and `initialize_database/` are called by nothing** in this
  repository. They date from the Configurator setting a study's database up;
  `setup/init_study_tables.py` does that now. Both sit behind the researcher login.
- **`android_tables_sql()` reads the deployment's own fragment**, so the
  Configurator and [db](db.md) cannot drift apart.

---

## Tests

```bash
python3 -m pytest AWARE-Configurator -q
```

Run from the repository root: `settings.py` resolves `PROJECT_ROOT` there and
imports `shared_config` from it. The integration module skips itself unless MySQL is
listening on `127.0.0.1:3306`.
