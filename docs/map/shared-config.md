# shared_config

The study model and everything derived from it. Imported by the deploy, the
Configurator and the read layer, so a question about the study is answered the same
way in all three. Prose: [`shared_config/README.md`](../../shared_config/README.md).

Runs on Python 3.12. No package of its own: every reader puts the repository root on
`sys.path` and imports it from there.

---

## What owns what

| Concept | File |
| --- | --- |
| Reading and updating `source.json`, under a lock | [`source_store.py`](../../shared_config/source_store.py) |
| The Android dataflow, and whether one can be honoured | [`dataflow.py`](../../shared_config/dataflow.py) |
| Where the database runs, bundled or external | [`placement.py`](../../shared_config/placement.py) |
| One declared host, resolved per reader, and the five accounts | [`database.py`](../../shared_config/database.py) |
| The Android and iOS configs built from the model | [`serializers.py`](../../shared_config/serializers.py) |
| Atomic writes, and which mode a written file carries | [`runtime.py`](../../shared_config/runtime.py) |
| Reaching a phone over MQTT topics the client already listens on | [`messaging.py`](../../shared_config/messaging.py) |
| How setup reaches the database, whichever placement | [`mysql_client.py`](../../shared_config/mysql_client.py) |
| A certificate, out of whatever it arrived wrapped in | [`certificates.py`](../../shared_config/certificates.py) |

---

## The names worth knowing

`read_source()`, `update_source(mutator)` and `source_lock()` are the only way to
touch the model. `update_source` takes a mutator and applies it inside the lock, so
a read-modify-write is one operation.

`placement.declared(source)` returns `BUNDLED` or `EXTERNAL`.
`dataflow.declared(source, "android")` returns `WEBSERVICE` or `DIRECT`, and
`dataflow.validate(source)` reports what a deployment cannot honour before anything
is generated. `ANDROID_STUDY_NUMBER` is 2, fixed.

`database.profiles()` derives the five accounts: `aware_android_participant`,
`aware_android_server`, `aware_ios_participant`, `aware_analytics`, `aware_backup`.

`runtime.SHARED_MODE` is `0o644`, for a file nginx or a container user reads.
`SECRET_MODE` is `0o600`, for one carrying a credential. `atomic_write_text` writes
through a temporary file and `os.replace`, so a reader sees a whole file or none.

`serializers.IOS_ONLY_SENSOR_NAMES` is `("significant_motion", "websocket", "mqtt")`.
These have no Android equivalent and must not be added to
`COMMON_SHARED_SENSOR_FIELDS`. `build_ios_sensor_settings` merges in three steps and
the last wins: the `ios.sensors` baseline, then `android.settings`, then the shared
frequency and threshold values. The function's own comments carry the rest, including
which keys are stripped before they can reach iOS.

---

## What changes together

- A **new sensor setting** has to reach the Android template, the serializer, and
  the Configurator's four front-end layers. See
  [configurator-frontend](configurator-frontend.md).
- **`source.example.json`** is the template a first deploy materialises. A field the
  model gains belongs there too, or a fresh study starts without it.
- **Windows** has no `fcntl`, so `source_lock()` yields without locking there. The
  atomic write still guarantees a whole file; what is given up is serialising two
  concurrent writers.

---

## Tests

```bash
python3 -m pytest shared_config -q
```

This suite covers more than the package. Test files here named for something outside
it are testing that thing from here: the scripts in [`setup/`](../../setup/README.md),
the schema in [`db/`](../../db/README.md), the nginx routes, and the documents,
including this map.
