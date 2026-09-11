# analytics_api

The read layer. FastAPI on Python 3.12, reading the study databases and answering
the dashboard. It writes nothing except the counts cache it maintains.
Prose: [`analytics_api/README.md`](../../analytics_api/README.md).

Routers hold the HTTP; services hold the logic and carry no FastAPI types. The
services are listed in
[the README's layout](../../analytics_api/README.md#layout). This note indexes the
routers, which it does not.

---

## The routers

One module per area, in
[`app/routers/`](../../analytics_api/app/routers), all mounted in
[`app/main.py`](../../analytics_api/app/main.py).

| Prefix | Module | Answers |
| --- | --- | --- |
| `/auth` | [`auth.py`](../../analytics_api/app/routers/auth.py) | The session, and the check nginx calls on every gated route |
| `/health` | [`health.py`](../../analytics_api/app/routers/health.py) | Whether the service is up |
| `/devices` | [`devices.py`](../../analytics_api/app/routers/devices.py) | The phones in the study, per platform |
| `/android/{device_id}` | [`android.py`](../../analytics_api/app/routers/android.py) | One Android phone's sensor series |
| `/ios/{device_id}` | [`ios.py`](../../analytics_api/app/routers/ios.py) | The same for an iPhone |
| `/study` | [`study.py`](../../analytics_api/app/routers/study.py) | Facts about the configuration, not about one phone |
| `/coverage` | [`coverage.py`](../../analytics_api/app/routers/coverage.py) | What a period holds, asked before anything is downloaded |
| `/export` | [`export.py`](../../analytics_api/app/routers/export.py) | The manifest, and the data itself |
| `/backup` | [`backup.py`](../../analytics_api/app/routers/backup.py) | Export and import of the whole databases |
| `/jobs` | [`jobs.py`](../../analytics_api/app/routers/jobs.py) | Status for any long-running job, whichever router started it |
| `/logs` | [`logs.py`](../../analytics_api/app/routers/logs.py) | Client operation logs |
| `/messages` | [`messages.py`](../../analytics_api/app/routers/messages.py) | Reaching a participant, and the record of having done it |
| `/counts` | [`counts.py`](../../analytics_api/app/routers/counts.py) | Maintenance of the record-count cache |
| `/live` | [`live.py`](../../analytics_api/app/routers/live.py) | The channel a dashboard listens on |

---

## Services the README's table leaves out

| Module | What it does |
| --- | --- |
| [`broker.py`](../../analytics_api/app/services/broker.py) | Publishing to the study broker, the one thing this system does outward |
| [`config_file.py`](../../analytics_api/app/services/config_file.py) | Reading a JSON config that changes underneath a running process |
| [`exclusions.py`](../../analytics_api/app/services/exclusions.py) | Devices a researcher has taken out of the analysis |
| [`export_size.py`](../../analytics_api/app/services/export_size.py) | Roughly how large an export will be, before producing it |
| [`orphan_rows.py`](../../analytics_api/app/services/orphan_rows.py) | Rows belonging to no device, counted rather than discarded |
| [`refusals.py`](../../analytics_api/app/services/refusals.py) | Writes the micro-server turned away, so an attempt is not invisible |
| [`sensor_tables.py`](../../analytics_api/app/services/sensor_tables.py) | Which physical tables a sensor's rows live in |

---

## What changes together

- **A table added in [db](db.md)** needs its SQLAlchemy model in
  [`app/models.py`](../../analytics_api/app/models.py), and a grant to
  `aware_analytics`, which is read-only everywhere except the counts cache.
- **A new endpoint** is a router plus a service plus a Pydantic schema in
  [`app/schemas.py`](../../analytics_api/app/schemas.py). No FastAPI type goes below
  the router.
- **`requirements-dev.txt` is compiled** from `requirements-dev.in`. A package added
  to the input reaches the suite only after `pip-compile`, and
  `tests/test_prerequisites.py` holds the two files together.

---

## Traps

- **Timestamps are milliseconds** since the epoch, held as `DOUBLE`.
- **Exclusion marks a device, it does not gate ingest.** A withdrawn participant's
  phone can still write; the enrolment gate in [micro-server](micro-server.md) is
  the only rule that stops a write.

---

## Tests

```bash
cd analytics_api && pytest -q
```

The integration tier needs a local `mysqld` and skips without one:
`pytest -m integration -q`. Details in [checks.md](../dev/checks.md).
