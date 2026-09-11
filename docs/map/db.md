# db

The MySQL schema, as a build product rather than a set of migrations. Applied with
`--init-file` on every start, so every statement in it is idempotent.
Prose: [`db/README.md`](../../db/README.md).

There are no migrations. A column is added by editing the fragment that declares the
table and guarding the `ALTER`, then rebuilding.

---

## What owns what

| Concept | File |
| --- | --- |
| The applied schema, generated | [`init_all.sql`](../../db/init_all.sql) |
| The builder, and its staleness check | [`build_init_all.py`](../../db/build_init_all.py) |
| Databases, accounts, grants | [`00-bootstrap.sql`](../../db/00-bootstrap.sql) |
| The Android data tables | [`android-tables.sql`](../../db/android-tables.sql) |
| The iOS data tables | [`ios-tables.sql`](../../db/ios-tables.sql) |
| Tables this project added: counts, refusals, enrolment, device contacts | [`dashboard-tables.sql`](../../db/dashboard-tables.sql) |
| What the AWARE client's providers declare | [`client_schema.py`](../../db/client_schema.py) |
| Account passwords, on a first start only | [`zz-account-passwords.sh`](../../db/zz-account-passwords.sh) |
| Freeing a sensor's label space | [`reclaim-sensor-label.sql`](../../db/reclaim-sensor-label.sql) |

---

## The build

`init_all.sql` is the concatenation of `00-bootstrap.sql`, `android-tables.sql`,
`ios-tables.sql` and `dashboard-tables.sql`, in that order. After editing any of
them:

```bash
python3 db/build_init_all.py
```

`--check` reports a stale product without writing, and CI runs it. A fragment edited
without a rebuild is a schema nobody applies.

`android-tables.sql` answers to the client rather than to this repository:
`client_schema.py` extracts the column list the Android client builds its `INSERT`
from. A column the server lacks makes every insert for that table fail silently.

---

## What changes together

- **A new table** has to be declared in the fragment for its platform, and granted
  to whichever of the five accounts touches it. The accounts are derived in
  [`shared_config/database.py`](../../shared_config/database.py); see
  [shared_config](shared-config.md).
- **`/docker-entrypoint-initdb.d` runs each `.sql` on its own**, with no database
  selected. Only `zz-account-passwords.sh` is mounted there. A fragment placed in
  that directory fails, because the fragments carry no `USE`.
- **The counts cache** in `dashboard-tables.sql` is maintained by the read layer off
  the request path. Its watermark is a per-sensor `_id`.

---

## Tests

```bash
python3 db/build_init_all.py --check
python3 -m pytest shared_config -q
```

The suite holds the generated schema to its fragments and to the client's declared
columns.
