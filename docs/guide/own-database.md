# Using a database of your own

The deployment can bring up a database of its own and manage everything inside it,
which is what most studies take. This page is for the other answer: a database you
name — your own server, your institution's, or one you rent from a provider.

It covers what the setup wizard will ask you for, what to arrange with whoever
administers the server, and how to check the connection before a study depends on
it. Nothing here applies to a deployment running its own database; see
[step 3 in the README](../../README.md#3-run-the-setup-script) for that path.

---

## Where the study database runs

Setup asks this in the network step, beside the dataflow, because the two decide
each other:

| Choice               | What it means                                                                                                                   |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| **On this machine**  | The deployment brings up its own MySQL container, creates the schema and manages the accounts. Nothing has to exist beforehand. |
| **Somewhere I name** | A host you give — your own server, your institution's, a managed instance. The deployment starts no database of its own.        |

**External is offered only when Android phones go through the server.** On the direct
path every participant's phone opens the database itself, from whatever network they
are on, so the host would have to be reachable from the internet for the length of
the study — which is a thing you can decide about a database you administer and not
one your institution does. The wizard disables the option rather than letting it be
chosen and refused later.

Choosing external takes the bundled database out of the deployment properly. Setup
writes `docker-compose.external-db.yml`, which removes the `mysql` service _and_ the
`depends_on` of the six services that wait on its health check — a service kept out
of a compose file is still depended on, and Compose starts a dependency whether or
not anyone asked for it. The file is generated from the choice and removed again when
you switch back, so its presence is the placement.

---

## Bringing your own managed database

**It has to be MySQL.** MySQL 8.0 or later, or a service that speaks its protocol
— MariaDB, Aurora MySQL, Percona. The whole stack reaches the database through the
MySQL client and `aiomysql`, and the schema is written in MySQL's dialect, so a
PostgreSQL-compatible service **cannot be used at all**, however the connection is
spelled. That rules out CockroachDB, Neon, Supabase, Render Postgres and anything
else whose selling point is Postgres compatibility — there is no setting that
bridges the two.

Where people usually get one:

| Service                                                                  | Notes                                                                                                                           |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------- |
| **Google Cloud SQL for MySQL**                                           | Paid. New accounts get trial credit; publishes its CA under _Connections → Security_.                                           |
| **Amazon RDS for MySQL**                                                 | Paid, with a 12-month free tier for new accounts on the smallest instance. Aurora MySQL is the same protocol at a higher price. |
| **Azure Database for MySQL**                                             | Paid, with a limited free tier for the first year.                                                                              |
| **DigitalOcean Managed MySQL**                                           | Paid, flat monthly price. _Download CA certificate_ button in the console.                                                      |
| **Aiven for MySQL**                                                      | Paid after a trial; CA certificate downloadable per service.                                                                    |
| **PlanetScale**                                                          | Paid, MySQL-compatible.                                                                                                         |
| **A VPS you run** (Hetzner, DigitalOcean droplet, your institution's VM) | Cheapest per gigabyte, and the schema, backups and TLS are then yours to manage.                                                |

Prices and free tiers change; check the current terms rather than trusting this
table. What does not change is the protocol: if the service does not say **MySQL**,
it will not work here.

A study collects in bursts when participants sync, not continuously, so the
smallest tier a provider offers is usually where to start. Storage is what grows —
high-frequency sensors like the accelerometer are the bulk of it.

**1. Create the instance.** MySQL 8.0 or later. The smallest tier a provider offers
is usually enough to start: a study writes in batches when participants sync, not
continuously.

**2. Let it be reached.** The database is opened from inside this deployment, so
allow the address of the machine running it. Providers call this different things —
_Authorized networks_ (Cloud SQL), _Trusted sources_ (DigitalOcean), _Allowed IP
addresses_ (Aiven), a security group (RDS). Nothing else has to be public: on the
webservice dataflow, no participant's phone ever contacts the database.

**3. Take an administrator account.** The one the provider created with the instance
is what setup uses to create the schema and the study's own accounts. Setup never
stores it; it is used for the deployment and then forgotten.

**4. Find the certificate authority, if the provider verifies one.** Managed
databases require TLS, and most publish a CA certificate to check them against:
Cloud SQL under _Connections → Security_, DigitalOcean and Aiven behind a _Download
CA certificate_ button, RDS and Azure as downloads in their documentation. Paste the
whole file — the `-----BEGIN CERTIFICATE-----` line included — into the wizard.
Leaving it empty still encrypts the connection; what it leaves unchecked is whether
the server answering is the one you meant.

**5. Paste what the provider gave you.** Managed services hand out a single line
like `mysql://user:password@db-123.example.cloud:25060/defaultdb?ssl-mode=REQUIRED`.
Paste it into **Database host** and the wizard takes it apart — host, port,
administrator account, and the password if you have not typed one. The parts land
in their own fields, so you can see what was understood and correct it.

Typing the host by hand works too, and the administrator account is then taken
from it — `avnadmin` for Aiven, `doadmin` for DigitalOcean, `root` for a server
you run. Change it if your provider named it something else. The port is yours to
copy: 3306 is MySQL's default and managed services rarely use it.

The database name is not asked for: the deployment creates its own schemas and
names them itself.

**The port is the usual trip-up.** 3306 is MySQL's default and most managed
services do not use it — Aiven and DigitalOcean give each database a port of its
own, often five digits. A wrong port looks exactly like a firewall: the name
resolves, nothing answers, and the check reports `Can't connect to MySQL server`.
If the port is right and it still times out, the provider is refusing this machine
— add its address under _Allowed IP addresses_ (Aiven), _Trusted sources_
(DigitalOcean) or _Authorized networks_ (Cloud SQL).

Pasting the whole string into the host field is caught by the wizard now, but the
reason it is worth knowing is that the string carries a password — one that ends up
in the deployment log if it reaches the check. Treat a connection string as a
credential, and rotate it if it has been pasted somewhere it should not have been.

---

## Testing the database before deploying, and who creates it

The database step has two controls that answer the questions people hit first.

**Test this database** asks what the deployment asks — reachable, schema present,
the study's accounts there, a row can be written — and shows each answer in the
wizard. It runs the same script the deployment does, so an answer here is the
answer there, and a database that cannot be reached becomes a field to correct
rather than a deployment that stops half way.

**Who creates the schema and the accounts** decides who does the work:

| Choice                   | What happens                                                                                                                                                                                      |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Setup does it**        | The deployment creates the schema and this study's accounts with the administrator account named above. Needs an account that may do that — managed databases usually give you one.               |
| **I run the SQL myself** | Setup creates nothing. **Download setup.sql** gives you the statements; run them, or hand them to whoever administers the server, then test again. The account setup uses then only has to write. |

The second is the usual answer at an institution, where the account you are given
may insert and nothing else. The file carries this study's account passwords, so
send it the way you would send a credential.

---

## Encryption to the database, and who decides it

Without TLS, MySQL 8 still protects the password and then carries every row of every
participant's data over the same socket in clear — the password was never the part
most worth protecting. So the connection is encrypted, and where the database runs
decides whether that is a question at all.

**On this machine, it is settled.** The deployment administers both ends: MySQL
generates its own certificate on first start, every account setup creates is granted
`REQUIRE SSL`, and there is no setting to turn it off. Offering one would be a way to
make a working study less safe in exchange for nothing.

**On a database you name, you answer it.** That server is not one this deployment
administers, and TLS there is something its owner offers or does not — an institutional
MySQL built without it, or a MariaDB older than 11.4 that generated no certificate.
Refusing those outright would refuse the study, so setup asks. The toggle is on by
default: nearly every server can encrypt, and setup opens the connection and reports
what actually happened before the study is deployed, so a server that cannot is found
there rather than weeks later as a study that enrolled and collected nothing. Turning
it off is recorded in the study model as `database.tls.require`, applied to every
account as `REQUIRE NONE`, and stated wherever the connection is described — the
wizard, the database check, and the Configurator's study page.

Encryption alone does not prove _which_ server answered. For a bundled database setup
solves that for you: MySQL generates its own certificate authority on first start, and
`deploy_config.py` reads it out of the container and publishes it in the study config,
so a participant's phone verifies the certificate chain. Nothing to enter. It is re-read
on every deploy, so a database that regenerates its certificate — a fresh volume, a
restored backup — publishes the authority it is actually using.

For a database you name elsewhere, only you can supply its authority. Paste it into the
setup wizard beside the host, or into the Configurator later; it is kept in the study
model as `database.tls.ca_certificate`. Setup verifies the server against it before the
study deploys. Without one the connection is encrypted but unverified: the traffic
cannot be read, and a server on the same network could impersonate the database.

> **A certificate authority that cannot be read stops collection.** The Android client
> treats an unparseable authority as a database it cannot reach — it keeps its data and
> stops uploading rather than quietly falling back to an unverified connection. That is
> the right behaviour, and it means a truncated or mistyped certificate halts the whole
> study until corrected. Setup refuses to publish one it cannot read, and `deploy_config.py`
> exits with an error rather than writing it. Leave it empty to run encrypted without
> verification.

---

## Getting a certificate authority for your own database

You only need this if you told setup to use **a database somewhere else** — a managed
one from a cloud provider, or a server you or your institution runs. If the deployment
runs its own database, this is already done for you and you can skip this section.

**What it is, in one paragraph.** Your database proves who it is by showing a
certificate, the way a website does. A certificate is only worth anything if somebody
vouched for it, and the one who vouches is called a _certificate authority_. Phones in
your study need a copy of that authority, otherwise they can encrypt the connection but
cannot tell your database apart from anything else answering at that address. What you
need is one small text file, and whoever hosts the database publishes it.

### Step 1 — find the file

It depends on where your database lives. In every case you are looking for the thing
the provider calls the **server CA certificate** — not a key, not a client certificate.

| Where the database runs                       | Where to find it                                                                                                                                                                                                           |
| --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Amazon RDS / Aurora**                       | Amazon publishes a certificate bundle for download; their docs call it the RDS certificate bundle. Search their documentation for _"SSL/TLS certificates for RDS"_ and take the bundle for your region, or the global one. |
| **Google Cloud SQL**                          | In the instance page, under **Connections → Security**, there is a server CA certificate you can download.                                                                                                                 |
| **Azure Database for MySQL**                  | Microsoft publishes the root certificate their servers use, with a download link in their _"Connect with encryption"_ documentation.                                                                                       |
| **DigitalOcean, Aiven, Scaleway and similar** | The database's page in the control panel has a **Download CA certificate** button.                                                                                                                                         |
| **A server your institution runs**            | Ask whoever administers it for the CA certificate used for TLS connections.                                                                                                                                                |
| **A server you run yourself**                 | If MySQL generated its own, it is `/var/lib/mysql/ca.pem` on that machine.                                                                                                                                                 |

If none of these match, search your provider's documentation for **"CA certificate"**
or **"SSL certificate download"**. Every provider that offers encrypted connections
publishes one.

### Step 2 — check you got the right thing

Open the file in any text editor. The right file:

- begins with the line `-----BEGIN CERTIFICATE-----`
- ends with the line `-----END CERTIFICATE-----`
- has a block of random-looking letters and numbers in between
- is small, a few dozen lines at most

Some providers give a _bundle_ holding several certificates one after another. That is
fine — paste the whole thing.

**If the file begins with `-----BEGIN PRIVATE KEY-----`, stop.** That is a secret key,
not a certificate, and it should not be shared or pasted anywhere. Go back and look for
the certificate instead.

### Step 3 — put it into the study

In the setup wizard, paste the **whole file** into the certificate authority field
under the database host — including the `BEGIN` and `END` lines. On a study that is
already deployed, the same field is in the Configurator under **Study information →
Database access**; paste it there and save.

Copy all of it. A certificate that is missing its first or last line, or has lost a
line in the middle, cannot be read — and an unreadable one stops collection (see the
warning below).

### Step 4 — check it worked

```bash
python3 setup/verify_database.py
```

The **Encrypted** line says which of these you have:

- _"Encrypted (…) and verified against the certificate authority this study supplies"_ —
  done.
- _"Encrypted (…). The certificate is not verified"_ — the connection is protected from
  being read, but no authority is supplied. Go back to step 1.
- _"This server's certificate does not check out against the authority this study
  supplies"_ — the file is a certificate but not the one that signed this server's.
  This fails the check rather than warning, because the phones would refuse the
  database too. Go back to step 1.

### If you cannot find the file

Leave the field empty. The study still works and the data is still encrypted — nobody
watching the network can read it. What you give up is the phones' ability to confirm
they are talking to _your_ database rather than to something pretending to be it. That
is a reasonable trade on a network you trust, and worth fixing when you can.

### One thing to be careful about

Devices treat a certificate authority they cannot read as a database they cannot reach:
they hold on to their data and **stop uploading**, rather than quietly connecting
without checking. That is deliberate — a study that thinks it is protected should not
silently be unprotected — but it means one mistyped or half-copied certificate can halt
the whole study until it is corrected. Setup refuses to publish a certificate it cannot
read, so a bad paste fails at deployment rather than on the phones.

---

## Checking the database before the study is committed to it

`setup/verify_database.py` runs on both placements and asks five questions:

| Check          | What it answers                                                                                                                                                                                              |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Reachable      | The address answers on its port and the credential authenticates                                                                                                                                             |
| Encrypted      | The connection is what the study asked of it, and — where an authority is supplied — the server's certificate checks out against it                                                                          |
| Schemas        | Both schemas this study's data lands in are there                                                                                                                                                            |
| Study accounts | Every account this deployment opens the database with — the one each Android dataflow puts on the ingest path, the iOS micro-server's, and the dashboard's own — connects with the password this study holds |
| Tables         | The tables a phone's rows land in are there                                                                                                                                                                  |

**The check creates nothing.** It opens the database as each account and reports what
is there; `setup/init_study_tables.py` is what makes it so, and it runs as part of
deploying. That split is what makes the answer worth having — a check that created
what it was asked about could only ever report success, and would report it against a
database you had not agreed to have changed yet.

So what is missing before the first deploy is not a failure. It is a line saying which
side is going to create it: setup, when it deploys, or whoever administers a database
setup may not touch.

Both schemas are asked about, and the tables as well as the accounts. An account
holding every grant its work needs on an empty schema collects nothing, and says so
only on the device — the client inserts into `accelerometer` and is told there is no
such table.

The client runs on the deployment's own network, so the question asked is the one the
micro-server and the API will ask; a host that resolves on your machine and not inside
a container is reported rather than accepted.

**An external database is checked before anything is generated.** If it fails, no
config a phone or a service reads is written and the deployment keeps running whatever
it ran before. The bundled one is checked once it is up, since it does not exist to be
asked before that.

**Missing privileges are reported, not assumed.** If your account cannot create the
schemas, the accounts or the tables — the usual case with an institutional database —
setup writes the whole thing out as one file for whoever administers the server: the
schemas, this study's accounts, and every table its data lands in. That file carries
this study's account passwords, so send it the way you would send a credential. Once
it has run, check again:

```bash
python3 setup/verify_database.py
```

---

## Switching between them

Changing the placement is a redeploy, not a live change, for the same reason changing
the dataflow is: it decides which containers exist. Re-run `setup.sh` and choose the
other option.

The change settles where the next row is written, and nothing else. Under **Keep from
the current setup** the wizard asks about the two things that would otherwise be
decided for you. Both are off unless switched on.

**Keep the data collected so far.** On, the deploy writes `copy-study-data.sh` and the
wizard shows the command:

```bash
sudo ./copy-study-data.sh
```

It dumps the old database from the container still holding it and loads it into the
new one, reading both passwords where they already live rather than carrying either.
Run it whenever suits — the study collects into the new database meanwhile — and run
it again if it stops, since every row goes in under the id the old server gave it. A
database that has already begun collecting is refused: inserting by id there would
drop the new rows as duplicates, and that case is a merge-import from the dashboard's
backup page instead. The dashboard's own counts are not copied; the first refresh on
the new server rebuilds them.

**Keep making backups.** On, the backup job stays, dumping the new database into the
same folder as `aware_analytics`, the account that may only read. Off, it is removed
along with the database it was written for, and copies are yours to arrange — your
provider's snapshots, or an export from the dashboard's backup page. The answer lives
in `.env` as `DB_KEEP_BACKUPS`, so a redeploy that skips the wizard keeps it.
