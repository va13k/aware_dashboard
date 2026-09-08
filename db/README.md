# The database

The schema both platforms' clients write into, the accounts that reach it, and the
one file MySQL is handed to build all of it.

In a deployment this directory is read by the `mysql` container. What it produces is
described from the deployment's side in
[docs/dev/architecture.md](../docs/dev/architecture.md#the-database); this document
is for working on the files themselves.

---

## One generated file, and the sources it comes from

MySQL applies the schema through `--init-file`, which it reads server-side and which
cannot `SOURCE` another file. So the whole schema has to arrive as one file, and
[`init_all.sql`](init_all.sql) is that file: a **build product**, with a banner
saying so.

```
00-bootstrap.sql     databases, accounts, grants
android-tables.sql   the Android schema
ios-tables.sql       the iOS schema
dashboard-tables.sql the tables the dashboard derives, and their grants
        │
        ▼  build_init_all.py
init_all.sql
```

[`build_init_all.py`](build_init_all.py) concatenates them and inserts the `USE`
statement each fragment needs:

```bash
python3 db/build_init_all.py            # regenerate
python3 db/build_init_all.py --check    # fail if it is stale
```

**`android-tables.sql` and `ios-tables.sql` carry no `USE` of their own.** They are
fragments, readable only inside `init_all.sql`, and a server handed one on its own
answers `No database selected`. `dashboard-tables.sql` is the exception: it carries
its own two `USE` statements and is appended last.

The check is part of the test suite, so a regeneration is asked for by
`pytest shared_config` rather than remembered.

---

## What runs when, and where

Three mechanisms, and telling them apart is most of understanding this directory.

| | Runs | Applies |
| --- | --- | --- |
| `--init-file=/etc/mysql/init_all.sql` | On **every** start of the server | The whole schema. Everything in it is idempotent, so a fresh server gets it from the `CREATE` statements and an existing one picks up later columns from guarded `ALTER` blocks |
| `/docker-entrypoint-initdb.d` | Once, on an **empty** data directory, after the init file | Only [`zz-account-passwords.sh`](zz-account-passwords.sh) is mounted there, because a shell script is the one thing an init file cannot be |
| By hand | When a deployment needs it | [`reclaim-sensor-label.sql`](reclaim-sensor-label.sql), described in [docs/guide/maintenance.md](../docs/guide/maintenance.md) |

**The directory itself is deliberately not mounted into
`/docker-entrypoint-initdb.d`.** MySQL runs each `.sql` file it finds there on its
own, which the fragments above cannot survive.

Idempotence is what makes the init file safe to replay: MySQL 8.0 has no
`ADD COLUMN IF NOT EXISTS`, so a later column arrives as an `ALTER` wrapped in a
check against `information_schema`, and a table already matching it is left alone.
That is also how a deployment upgrades: there is no migration step and no version
to compare.

---

## The accounts

[`00-bootstrap.sql`](00-bootstrap.sql) creates the databases and every account, each
with a password written into this repository. Those are a **first-boot seed and
nothing more**: `zz-account-passwords.sh` replaces them with this deployment's own
on the same first start, and it treats a missing password variable as fatal rather
than as a warning, since carrying on would leave a database whose password is
published.

`CREATE USER IF NOT EXISTS` throughout is what lets the init file replay on every
later start without resetting those passwords.

Which account is granted what, and why each is narrow, is in
[`shared_config/database.py`](../shared_config/database.py), where `profiles()`
derives the list every reader shares. The grants here have to agree with it: an
account created here and missing from there is one the deployment never opens, and
the other way round is a deploy that fails on a password for an account that does
not exist.

---

## Holding the schema to the client

The Android client builds its `INSERT` column list from its own `TABLES_FIELDS`
declaration, so **a column the server lacks makes every insert for that table fail
silently**. Nothing on the phone reports it, and the row simply never arrives.

[`client_schema.py`](client_schema.py) reads that declaration out of the client's
Java sources, and the build script compares it against the Android schema:

```bash
python3 db/build_init_all.py --check-client ../aware-client
```

It needs a checkout of the client, so it is run by hand when the client changes
rather than by the suite.

---

## Working on it

- **Adding a column to a sensor table** means adding it to the fragment *and* a
  guarded `ALTER` beside it, so servers that already exist pick it up. Then
  regenerate.
- **Adding a table the dashboard derives** belongs in `dashboard-tables.sql`, with
  its grant beside it: `aware_analytics` reads the study schemas and writes only the
  tables it maintains.
- **Never edit `init_all.sql`.** Its first line says so, and the suite will say it
  again.
