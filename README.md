# AWARE Dashboard

A self-hosted research platform for collecting and visualising sensor data from Android and iOS devices. The entire stack is bundled into a single Docker Compose project that you can deploy with one command.

## What it is

Study participants install the **AWARE client app** on their phone (Android or iOS). The app continuously collects sensor data — accelerometer, GPS, screen events, ambient noise, and [many more](#sensor-support). Due to security restrictions on both Android and iOS, participants must **manually trigger a data upload** from inside the app. Once they do, the data is sent to your server and becomes immediately available in the analytics dashboard for browsing, filtering, and export.

The full stack comprises six services:

| Service                                                                        | Role                                                                                        |
| ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------- |
| **Nginx**                                                                      | Reverse proxy — routes all public traffic, terminates TLS, enforces authentication          |
| **Analytics API**                                                              | FastAPI backend for the dashboard — queries the database and serves sensor data and exports |
| **Analytics Dashboard**                                                        | React frontend — visualises collected data per device and sensor; exports CSVs and ZIPs     |
| [**AWARE Configurator**](https://github.com/awareframework/AWARE-Configurator) | Django + React app for building and publishing study configurations for Android and iOS     |
| [**AWARE Micro Server**](https://github.com/awareframework/aware-micro-server) | Kotlin / Vert.x server that receives data uploads from iOS clients and writes them to MySQL |
| **MySQL + backup**                                                             | Shared database for all collected data, with a configurable automated backup job            |

A browser-based **setup wizard** is included for the initial deployment — it writes your configuration and launches the stack without any manual file editing.

### Client apps

Study participants need the AWARE mobile app installed on their device:

- **Android** and **iOS** clients are available at [awareframework.com/downloads](https://awareframework.com/downloads/)

Once a participant joins a study (by scanning a QR code or entering a study URL), the app begins collecting sensor data locally and waits for the participant to manually sync it to the server.

## Prerequisites

### Docker with Compose v2

The entire stack runs in Docker. No other runtime (Node, Java, etc.) needs to be installed on the host.

| Platform | What to install                                                                                                             |
| -------- | --------------------------------------------------------------------------------------------------------------------------- |
| macOS    | [Docker Desktop](https://www.docker.com/products/docker-desktop/) — Compose v2 is included                                  |
| Windows  | [Docker Desktop](https://www.docker.com/products/docker-desktop/) — Compose v2 is included                                  |
| Linux    | [Docker Engine](https://docs.docker.com/engine/install/) + [Compose plugin](https://docs.docker.com/compose/install/linux/) |

### Python 3

The setup scripts (`setup.sh` / `setup.bat`) run several Python 3 helper scripts directly on the host to generate config files and initialise the database. No third-party packages are required — only the Python standard library.

| Platform | How to get it                                                                                                         |
| -------- | --------------------------------------------------------------------------------------------------------------------- |
| macOS    | Pre-installed on most systems, or install via [Homebrew](https://brew.sh/): `brew install python3`                    |
| Windows  | Download from [python.org](https://www.python.org/downloads/) — tick **"Add Python to PATH"** during installation     |
| Linux    | Usually pre-installed. If not: `sudo apt install python3` (Debian/Ubuntu) or `sudo dnf install python3` (RHEL/Fedora) |

Verify with: `python3 --version` (Linux/macOS) or `python --version` (Windows).

### Git

| Platform | How to get it                                                                                                                 |
| -------- | ----------------------------------------------------------------------------------------------------------------------------- |
| macOS    | Pre-installed via Xcode Command Line Tools: `xcode-select --install`, or via [Homebrew](https://brew.sh/): `brew install git` |
| Windows  | Download from [git-scm.com](https://git-scm.com/download/win) — use the default options during installation                   |
| Linux    | `sudo apt install git` (Debian/Ubuntu) or `sudo dnf install git` (RHEL/Fedora)                                                |

Verify with: `git --version`.

### Network ports

| Port   | Purpose                                                          |
| ------ | ---------------------------------------------------------------- |
| `80`   | Main HTTP access — required                                      |
| `443`  | HTTPS — required only if you enable TLS                          |
| `9999` | Setup wizard — only needed temporarily during initial deployment |

If you are deploying on a remote server, open ports `80` and `443` in your firewall before running setup. Port `9999` only needs to be reachable from your own machine during the setup step and can be closed afterwards.

Treat the wizard URL as a credential while it is up. The page behind that token holds this deployment's database password and the researcher's own, and it is served over plain HTTP, so the token is what stands between them and anyone who can reach port `9999`. `setup.sh` removes the wizard container when setup finishes. On a network you do not trust, set `SETUP_BIND=127.0.0.1` in `.env` before running setup and reach the wizard through an SSH tunnel instead — see [Remote server deployment](#remote-server-deployment).

### SSL certificate (optional, recommended for remote servers)

If you want HTTPS, obtain a certificate for your domain before running setup — for example with [Let's Encrypt / Certbot](https://certbot.eff.org/). The setup wizard will ask for the paths to the certificate and private key files.

## How to perform the deployment

### 1. Open a terminal

You will type all the commands below into a terminal (command-line) window. Here is how to open one:

| OS          | How to open a terminal                                                                                         |
| ----------- | -------------------------------------------------------------------------------------------------------------- |
| **macOS**   | Press **⌘ + Space**, type **Terminal**, press Enter                                                            |
| **Windows** | Press **Win + S**, type **PowerShell**, right-click **Windows PowerShell** and choose **Run as administrator** |
| **Linux**   | Press **Ctrl + Alt + T**, or search for **Terminal** in your application menu                                  |

Once the terminal is open, you can copy each command below and paste it in, then press **Enter** to run it. Do this one command at a time and wait for each one to finish before moving to the next.

### 2. Clone the repository

When a terminal opens, it places you in a default location on your computer — usually your home folder (something like `C:\Users\yourname` on Windows or `/Users/yourname` on macOS). You can clone the project anywhere you like, but it is a good idea to keep code in a dedicated folder so it is easy to find later.

For example, to create a `dev` folder and clone into it:

```bash
mkdir dev
cd dev
git clone https://github.com/va13k/aware_dashboard.git
cd aware_dashboard
```

What each command does:

- `mkdir dev` — creates a new folder called `dev` in your current location
- `cd dev` — moves you into that folder
- `git clone ...` — downloads the project into a new subfolder called `aware_dashboard`
- `cd aware_dashboard` — moves you into the project folder

All following commands must be run from inside the `aware_dashboard` folder. You can confirm you are in the right place by checking that your terminal prompt shows `aware_dashboard` at the end of the path.

### 3. Run the setup script

Before running the script, **make sure Docker Desktop is open and fully started**. You should see the Docker whale icon in your taskbar (Windows) or menu bar (macOS) and it should not be showing a loading spinner — if it is still starting up, wait until it settles before continuing.

> On Linux, Docker runs as a background service and does not need a Desktop app — you can skip this step.

Once Docker is running, start the guided setup wizard with the command that matches your operating system:

**macOS / Linux:**

```bash
./setup.sh
```

**Windows (PowerShell):**

```bat
./setup.bat
```

> **Windows note:** If you get a message saying the script is not recognised, make sure you are in the `aware_dashboard` folder (you should see it in the prompt) and that Docker Desktop is running before you try again.

The script checks that Docker and Python 3 are available, then does the following automatically:

1. **Detects your machine's IP address** — it inspects your network interfaces and picks the best non-loopback, non-virtual address (e.g. `192.168.1.42`). It avoids Docker bridge interfaces, VPN adapters, and loopback.
2. **Starts the setup wizard** as a temporary Docker container on port `9999`.
3. **Prints the wizard URL** in the terminal — it looks like:
   ```
   http://192.168.1.42:9999/KL0XF9tXQVC4LRY-gCTRDWEQhO6II3IOLxU4/
   ```
   The path contains a one-time random token that is valid for this session only, and it is the
   only thing guarding a page that holds this deployment's passwords — so do not paste it into
   a chat or an issue.
4. **Tries to open the URL in your browser** automatically (macOS and Linux with a desktop). On a headless server, this step does nothing — see [Remote server deployment](#remote-server-deployment) below.

Once the setup page opens in your browser — either automatically or after you copied the URL from the terminal — you are ready to continue. **Proceed to [Step 3 — Complete the setup wizard](#3-complete-the-setup-wizard).**

### Re-running setup

If `.env` already exists, the script detects them and offers a choice:

```
  Existing configuration found (.env)

  1) Deploy with current config
  2) Edit configuration first

  Choose [1/2]:
```

- **Option 1** — skips the wizard and redeploys immediately with the saved config.
- **Option 2** — opens the wizard again so you can change any settings before deploying.

Both options re-apply `PARTICIPANT_DB_PASSWORD` and `ANDROID_SERVER_DB_PASSWORD` to their MySQL accounts, so the passwords in `.env` and the ones the study needs never drift apart. If you edited a password directly in `.env`, run `setup.sh` (or `python3 setup/init_study_tables.py`) rather than `docker compose up` on its own — starting the containers by hand leaves the existing database untouched, and the accounts keep their old passwords.

### Where the study database runs

Setup asks this in the network step, beside the dataflow, because the two decide
each other:

| Choice | What it means |
| --- | --- |
| **On this machine** | The deployment brings up its own MySQL container, creates the schema and manages the accounts. Nothing has to exist beforehand. |
| **Somewhere I name** | A host you give — your own server, your institution's, a managed instance. The deployment starts no database of its own. |

**External is offered only when Android phones go through the server.** On the direct
path every participant's phone opens the database itself, from whatever network they
are on, so the host would have to be reachable from the internet for the length of
the study — which is a thing you can decide about a database you administer and not
one your institution does. The wizard disables the option rather than letting it be
chosen and refused later.

Choosing external takes the bundled database out of the deployment properly. Setup
writes `docker-compose.external-db.yml`, which removes the `mysql` service *and* the
`depends_on` of the six services that wait on its health check — a service kept out
of a compose file is still depended on, and Compose starts a dependency whether or
not anyone asked for it. The file is generated from the choice and removed again when
you switch back, so its presence is the placement.

### Bringing your own managed database

**It has to be MySQL.** MySQL 8.0 or later, or a service that speaks its protocol
— MariaDB, Aurora MySQL, Percona. The whole stack reaches the database through the
MySQL client and `aiomysql`, and the schema is written in MySQL's dialect, so a
PostgreSQL-compatible service **cannot be used at all**, however the connection is
spelled. That rules out CockroachDB, Neon, Supabase, Render Postgres and anything
else whose selling point is Postgres compatibility — there is no setting that
bridges the two.

Where people usually get one:

| Service | Notes |
| --- | --- |
| **Google Cloud SQL for MySQL** | Paid. New accounts get trial credit; publishes its CA under *Connections → Security*. |
| **Amazon RDS for MySQL** | Paid, with a 12-month free tier for new accounts on the smallest instance. Aurora MySQL is the same protocol at a higher price. |
| **Azure Database for MySQL** | Paid, with a limited free tier for the first year. |
| **DigitalOcean Managed MySQL** | Paid, flat monthly price. *Download CA certificate* button in the console. |
| **Aiven for MySQL** | Paid after a trial; CA certificate downloadable per service. |
| **PlanetScale** | Paid, MySQL-compatible. |
| **A VPS you run** (Hetzner, DigitalOcean droplet, your institution's VM) | Cheapest per gigabyte, and the schema, backups and TLS are then yours to manage. |

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
*Authorized networks* (Cloud SQL), *Trusted sources* (DigitalOcean), *Allowed IP
addresses* (Aiven), a security group (RDS). Nothing else has to be public: on the
webservice dataflow, no participant's phone ever contacts the database.

**3. Take an administrator account.** The one the provider created with the instance
is what setup uses to create the schema and the study's own accounts. Setup never
stores it; it is used for the deployment and then forgotten.

**4. Find the certificate authority, if the provider verifies one.** Managed
databases require TLS, and most publish a CA certificate to check them against:
Cloud SQL under *Connections → Security*, DigitalOcean and Aiven behind a *Download
CA certificate* button, RDS and Azure as downloads in their documentation. Paste the
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
— add its address under *Allowed IP addresses* (Aiven), *Trusted sources*
(DigitalOcean) or *Authorized networks* (Cloud SQL).

Pasting the whole string into the host field is caught by the wizard now, but the
reason it is worth knowing is that the string carries a password — one that ends up
in the deployment log if it reaches the check. Treat a connection string as a
credential, and rotate it if it has been pasted somewhere it should not have been.

### Testing the database before deploying, and who creates it

The database step has two controls that answer the questions people hit first.

**Test this database** asks what the deployment asks — reachable, schema present,
the study's accounts there, a row can be written — and shows each answer in the
wizard. It runs the same script the deployment does, so an answer here is the
answer there, and a database that cannot be reached becomes a field to correct
rather than a deployment that stops half way.

**Who creates the schema and the accounts** decides who does the work:

| Choice | What happens |
| --- | --- |
| **Setup does it** | The deployment creates the schema and this study's accounts with the administrator account named above. Needs an account that may do that — managed databases usually give you one. |
| **I run the SQL myself** | Setup creates nothing. **Download setup.sql** gives you the statements; run them, or hand them to whoever administers the server, then test again. The account setup uses then only has to write. |

The second is the usual answer at an institution, where the account you are given
may insert and nothing else. The file carries this study's account passwords, so
send it the way you would send a credential.

### Encryption to the database, and who decides it

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

Encryption alone does not prove *which* server answered. For a bundled database setup
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

### Getting a certificate authority for your own database

You only need this if you told setup to use **a database somewhere else** — a managed
one from a cloud provider, or a server you or your institution runs. If the deployment
runs its own database, this is already done for you and you can skip this section.

**What it is, in one paragraph.** Your database proves who it is by showing a
certificate, the way a website does. A certificate is only worth anything if somebody
vouched for it, and the one who vouches is called a *certificate authority*. Phones in
your study need a copy of that authority, otherwise they can encrypt the connection but
cannot tell your database apart from anything else answering at that address. What you
need is one small text file, and whoever hosts the database publishes it.

#### Step 1 — find the file

It depends on where your database lives. In every case you are looking for the thing
the provider calls the **server CA certificate** — not a key, not a client certificate.

| Where the database runs | Where to find it |
| --- | --- |
| **Amazon RDS / Aurora** | Amazon publishes a certificate bundle for download; their docs call it the RDS certificate bundle. Search their documentation for *"SSL/TLS certificates for RDS"* and take the bundle for your region, or the global one. |
| **Google Cloud SQL** | In the instance page, under **Connections → Security**, there is a server CA certificate you can download. |
| **Azure Database for MySQL** | Microsoft publishes the root certificate their servers use, with a download link in their *"Connect with encryption"* documentation. |
| **DigitalOcean, Aiven, Scaleway and similar** | The database's page in the control panel has a **Download CA certificate** button. |
| **A server your institution runs** | Ask whoever administers it for the CA certificate used for TLS connections. |
| **A server you run yourself** | If MySQL generated its own, it is `/var/lib/mysql/ca.pem` on that machine. |

If none of these match, search your provider's documentation for **"CA certificate"**
or **"SSL certificate download"**. Every provider that offers encrypted connections
publishes one.

#### Step 2 — check you got the right thing

Open the file in any text editor. The right file:

- begins with the line `-----BEGIN CERTIFICATE-----`
- ends with the line `-----END CERTIFICATE-----`
- has a block of random-looking letters and numbers in between
- is small, a few dozen lines at most

Some providers give a *bundle* holding several certificates one after another. That is
fine — paste the whole thing.

**If the file begins with `-----BEGIN PRIVATE KEY-----`, stop.** That is a secret key,
not a certificate, and it should not be shared or pasted anywhere. Go back and look for
the certificate instead.

#### Step 3 — put it into the study

In the setup wizard, paste the **whole file** into the certificate authority field
under the database host — including the `BEGIN` and `END` lines. On a study that is
already deployed, the same field is in the Configurator under **Study information →
Database access**; paste it there and save.

Copy all of it. A certificate that is missing its first or last line, or has lost a
line in the middle, cannot be read — and an unreadable one stops collection (see the
warning below).

#### Step 4 — check it worked

```bash
python3 setup/verify_database.py
```

The **Encrypted** line says which of these you have:

- *"Encrypted (…) and verified against the certificate authority this study supplies"* —
  done.
- *"Encrypted (…). The certificate is not verified"* — the connection is protected from
  being read, but no authority is supplied. Go back to step 1.
- *"This server's certificate does not check out against the authority this study
  supplies"* — the file is a certificate but not the one that signed this server's.
  This fails the check rather than warning, because the phones would refuse the
  database too. Go back to step 1.

#### If you cannot find the file

Leave the field empty. The study still works and the data is still encrypted — nobody
watching the network can read it. What you give up is the phones' ability to confirm
they are talking to *your* database rather than to something pretending to be it. That
is a reasonable trade on a network you trust, and worth fixing when you can.

#### One thing to be careful about

Devices treat a certificate authority they cannot read as a database they cannot reach:
they hold on to their data and **stop uploading**, rather than quietly connecting
without checking. That is deliberate — a study that thinks it is protected should not
silently be unprotected — but it means one mistyped or half-copied certificate can halt
the whole study until it is corrected. Setup refuses to publish a certificate it cannot
read, so a bad paste fails at deployment rather than on the phones.

### Checking the database before the study is committed to it

`setup/verify_database.py` runs on both placements and asks five questions:

| Check | What it answers |
| --- | --- |
| Reachable | The address answers on its port and the credential authenticates |
| Encrypted | The connection is what the study asked of it, and — where an authority is supplied — the server's certificate checks out against it |
| Schemas | Both schemas this study's data lands in are there |
| Study accounts | Every account this deployment opens the database with — the one each Android dataflow puts on the ingest path, the iOS micro-server's, and the dashboard's own — connects with the password this study holds |
| Tables | The tables a phone's rows land in are there |

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

### Switching between them

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

### Checking the ingest path before anyone enrols

Setup runs `setup/verify_ingest.py` once the containers report healthy, and both the
terminal and the wizard page show what it found. It asks the deployment the question a
participant's phone will ask, at the study's public address rather than over the
compose network:

| Check | What it answers |
| --- | --- |
| Endpoint reachable | The address the study hands out answers, with the configuration a joining phone reads |
| Certificate | On HTTPS, the certificate that address presents verifies, and when it expires |
| Test record lands | A row posted the way the client posts one is admitted and is in the study database afterwards |
| Probe removed | Everything the check wrote has been taken back out |

Both dataflows are covered. On `webservice` the row goes over HTTPS to the Android
micro-server; on `direct` it is written by the participant account over MySQL's
published port, which is what a phone opens on that path.

The check writes as a synthetic device named `setup-self-test-…`, and removes its row,
its enrolment window and its entries in `record_counts`, `coverage_hourly` and
`refusals` — all of which are keyed by device, so the study's own figures are untouched.
If a run is interrupted, its rows are still addressable by that prefix.

A failure does not stop the deployment: the stack is up either way. It means phones
enrolled now would collect data and never deliver it, so fix what it reports and run it
again:

```bash
python3 setup/verify_ingest.py
```

### Reclaiming sensor label space

The ten physical sensor tables are created without a `label` column. The client
fills that column from an Android broadcast a study never sends, so on a database
created before it was dropped it holds one empty string per row across the
highest-volume tables. `db/reclaim-sensor-label.sql` removes it there:

```bash
docker exec -i aware_mysql mysql -uroot -p<root-password> aware_android < db/reclaim-sensor-label.sql
```

The script reports each table it touches and can be re-run: a table already
matching the schema is left alone. `bluetooth`, `locations` and `wifi` keep their
`label`, which the client writes.

### Remote server deployment

On a Linux server without a graphical desktop, the browser cannot open automatically. The URL is still printed in the terminal — copy it and open it from your own computer.

For the wizard to be reachable from your computer, the server's port `9999` must be
accessible. Two ways to do this:

**Option A — Temporarily open port 9999**

Open port `9999` in your firewall, copy the full URL the script printed, open it in your
browser, complete setup, then close the port again. This is the shortest path and the one the
script assumes.

**Option B — SSH tunnel (nothing is exposed at any point)**

Put `SETUP_BIND=127.0.0.1` in `.env` before running setup, so the wizard listens on the server
itself and nowhere else. Then, on your own computer:

```bash
ssh -N -L 9999:localhost:9999 your-user@your-server-ip
```

Open the URL the script printed with `localhost` in place of the server's address. Worth the
extra step on a shared or untrusted network: the wizard serves this deployment's database
password and the researcher's own over plain HTTP, and the token guarding them travels in the
URL in clear text.

### 3. Complete the setup wizard

The wizard has five steps. A progress bar at the top tracks where you are. You can go back to any previous step before deploying.

---

**Step 1 — Database**

Set the **database administrator** and its password. This is the account that creates the schemas, this study's own accounts and its tables. On a database you name it is the one your provider handed you — `avnadmin` on Aiven, `doadmin` on DigitalOcean. On the bundled database setup creates an account with the name you give and grants it what running the study needs; MySQL's own `root` keeps a password setup generates and nobody types, so moving a study between the two never overwrites either.

Set the **participant device password** as well. This is the password of the MySQL account that participant devices use to insert their data, and it is the password participants type on their phone when the study configuration is served without an embedded password (the **Configure without password** option in the Configurator).

- Use the **Generate** button to create a random one, or type your own — letters, digits and `. _ ~ @ # % ^ * + = : -` are allowed.
- Leave it blank to keep the password the deployment already uses, or to have one generated on a fresh install.
- On a re-run, the field is pre-filled with the current password. Changing it here applies the new password to the MySQL accounts on the next deployment, so any device still holding the old one must be given the new password.
- The wizard shows the password again on the completion screen, and it is stored as `PARTICIPANT_DB_PASSWORD` in `.env`. You can also set it there before running `setup.sh`.

This password belongs to the account a phone opens the database with, which is what the **straight to the database** dataflow asks of a phone. On the **through the server** dataflow no phone opens MySQL at all: the micro-server performs every write, with an account of its own — `aware_android_server` — and its own password, generated into `ANDROID_SERVER_DB_PASSWORD`. Nothing publishes that one, and the Configurator's Database access step edits whichever of the two the study's dataflow puts on the ingest path, naming the account it is changing.

The two accounts are granted different things, because they do different work:

| Account | Granted | Used by |
| --- | --- | --- |
| `aware_android_participant` | `INSERT` on the Android schema | A participant's phone, on the straight-to-the-database dataflow |
| `aware_android_server` | `INSERT` on the Android schema, plus reading `device_enrolment`, keeping `refusals`, and updating `aware_device` | The Android micro-server, on the through-the-server dataflow |
| `aware_analytics` | `SELECT` on both schemas, with write on the dashboard's own cache tables | The dashboard's API and its refresher |

Separate passwords, because the participant one is embedded in the study config every phone downloads, while the server's account can read the enrolment registry a phone's account cannot.

The database also applies built-in connection protection for participant devices:

- repeated failed logins are progressively delayed after three attempts, up to five seconds;
- incomplete connection handshakes time out after five seconds;
- each MySQL account may use at most 100 simultaneous authenticated connections by default.

The connection ceiling limits concurrent database work, not enrolled participants. Set
`MYSQL_MAX_USER_CONNECTIONS_PER_ACCOUNT` in `.env` to change the persistent value on the
next MySQL container recreation. To change the running server immediately without a
restart, use MySQL's `SET GLOBAL max_user_connections = ...` statement as well.

---

**Step 2 — Researcher access**

Set the **username and password** for the researcher login. These credentials protect the dashboard, configurator, and backup pages from being accessed by study participants.

- The username defaults to `researcher` on a fresh install.
- Use the **Generate** button to create a random secure password.
- On a re-run, the username is pre-filled from the existing config. Leave the password field blank to keep the current password unchanged.

Save these credentials — you will need them every time you log in to the protected pages.

---

**Step 3 — Network**

This step decides how participant devices reach your server. Choose the option that matches where you are deploying.

---

**Use detected local IP** *(default)*

The setup script automatically detects your computer's local network IP address (e.g. `192.168.1.42`). This is the right choice when:

- The server runs on your laptop or desktop
- Participant phones are on **the same Wi-Fi network** as the server

With this setup, phones and the server talk directly over your local network — no internet connection required. It is ideal for lab studies or pilot testing where you control the network.

> **If the detected IP looks wrong** — for example it shows a Docker internal address like `172.x.x.x`, or `localhost` — switch to **Enter another host manually** and type your actual LAN IP.
> To find it: **Windows** — open Command Prompt and run `ipconfig`, look for "IPv4 Address" under your Wi-Fi or Ethernet adapter. **Mac** — open System Settings → Network → click your active connection.

---

**Use localhost**

`localhost` (also reachable as `127.0.0.1`) is a completely isolated environment — it exists only inside the machine where the server is running and is not reachable from any other device, including phones on the same Wi-Fi.

This option is only useful when you are testing with software emulators running on the same machine as the server:

- **Android emulator** — [Android Studio](https://developer.android.com/studio) includes an Android emulator. Inside the emulator, use `10.0.2.2` to reach the host machine's `localhost`.
- **iOS simulator** — [Xcode](https://developer.apple.com/xcode/) includes an iPhone simulator. It shares the host network, so `localhost` works directly inside the simulator.

> Real phones on Wi-Fi **cannot** reach `localhost`. Use the local IP option for physical devices.

---

**Enter another host manually**

Use this when deploying on a **remote server** accessible over the internet, or when the detected IP is incorrect. Enter either:

- A **domain name** (e.g. `study.example.com`) — the cleanest option for a real deployment. You need a domain registered and pointing to your server's public IP.
- A **public IP address** — possible but less reliable; IP addresses can change.

Popular cloud providers for hosting a study server:

| Provider | Notes |
| --- | --- |
| [DigitalOcean Droplet](https://www.digitalocean.com/products/droplets) | Simple, affordable, good starting point |
| [Hetzner Cloud](https://www.hetzner.com/cloud/) | Very affordable European option |
| [AWS EC2](https://aws.amazon.com/ec2/) | Widely used, more configuration required |
| [Google Cloud Compute Engine](https://cloud.google.com/compute) | Similar to AWS |
| [Azure Virtual Machines](https://azure.microsoft.com/en-us/products/virtual-machines) | Microsoft's offering |

Any Linux VPS (Ubuntu 22.04 or later recommended) with Docker installed will work.

---

**Enable HTTPS**

> **If your server is accessible over the internet, enable HTTPS.** Without it, all data sent from participant phones — sensor readings, locations, and everything else — travels as plain text that anyone on the network path can read. HTTPS encrypts the connection end-to-end.

Toggle HTTPS on if you have SSL certificates. Two additional fields appear:

- **Certificate path** — path to your `fullchain.pem` file (default: `./certs/fullchain.pem`)
- **Key path** — path to your `privkey.pem` file (default: `./certs/privkey.pem`)

Both paths can be relative to the project folder or absolute.

HTTPS is **not required** for local network deployments (same Wi-Fi) or localhost testing.

#### How to get a free SSL certificate with Let's Encrypt

[Let's Encrypt](https://letsencrypt.org/) issues free, trusted certificates automatically. The official tool for obtaining them is [Certbot](https://certbot.eff.org/). You need:

- A **domain name** pointing at your server's public IP (e.g. `study.example.com` with an A record set in your DNS provider)
- **Port 80 open** on the server (for the domain-ownership challenge)

For a full walkthrough, follow the **[DigitalOcean guide: How To Secure Nginx with Let's Encrypt on Ubuntu 22.04](https://www.digitalocean.com/community/tutorials/how-to-secure-nginx-with-let-s-encrypt-on-ubuntu-22-04)** — it is the most widely used step-by-step reference and covers everything from installation to auto-renewal.

**Summary of the key steps on Ubuntu/Debian:**

```bash
# 1. Install Certbot via snap (recommended by the official Certbot site)
sudo snap install --classic certbot
sudo ln -s /snap/bin/certbot /usr/local/bin/certbot

# 2. Obtain the certificate (certonly — because Nginx runs inside Docker,
#    not as a system service, so Certbot should not auto-edit its config)
sudo certbot certonly --standalone -d your-domain.com

# 3. Test that automatic renewal works (certificates expire every 90 days;
#    Certbot schedules renewal automatically via a systemd timer)
sudo certbot renew --dry-run
```

After step 2, your certificate files are at:

```
/etc/letsencrypt/live/your-domain.com/fullchain.pem
/etc/letsencrypt/live/your-domain.com/privkey.pem
```

Enter these absolute paths in the wizard's **Certificate path** and **Key path** fields (or copy them into the `certs/` folder inside the project and use the relative defaults).

> **`--standalone` vs `--nginx`:** The `--standalone` flag tells Certbot to spin up its own temporary web server on port 80 to prove domain ownership — this works even when your Docker containers are not yet running. If your containers are already running and occupying port 80, stop them first with `sudo docker compose stop`, run certbot, then start them again. The `--nginx` flag would try to configure the system-level Nginx, which is not what you want here since Nginx runs inside Docker.

---

**Step 4 — Backups**

Configure automated MySQL backups. Backups are saved directly on the host machine (outside Docker volumes) so they survive a `docker compose down -v`.

- **Backup folder** — where to save the backup files. Relative paths are resolved from the project folder. The path must not contain spaces.
- **Backup interval** — how often a backup runs, in days (default: 1).
- **Keep backups for** — how many days to retain backups before they are deleted (default: 30).

---

**Step 5 — Review**

Shows a preview of the `.env` file that will be written. Review the values and click **Deploy** when ready.

---

**Deploying**

After you click Deploy, the wizard:

1. Writes `.env`, `aware-micro-server/aware-config.json`, and `studies/index.html`
2. Builds all Docker images
3. Starts all seven services and polls their health checks every 1.5 seconds
4. Shows which services are still starting (e.g. `Waiting for: mysql, configurator`)
5. On success — displays the researcher credentials one final time and redirects your browser to the main page after 2.5 seconds

If deployment fails, an error message is shown and an **Edit configuration** button lets you go back and fix the settings.

### 4. What you can access

Once deployment is complete, open the main page at `http://your-host/` (or `https://` if you enabled TLS).

The main page links to all four sections of the platform:

| Page                    | URL              | Access                     |
| ----------------------- | ---------------- | -------------------------- |
| **Join the study**      | `/studies/`      | Public — no login required |
| **Configurator**        | `/configurator/` | Researcher login required  |
| **Analytics Dashboard** | `/dashboard/`    | Researcher login required  |
| **Backup & Restore**    | `/backup/`       | Researcher login required  |

**Join the study** is intentionally public so that participants can reach it without credentials. It asks which phone they have and then shows only that platform's steps: where to get the app, the join URL to copy, and the QR code to scan. The page guesses the platform from the browser and lets them switch.

All other pages are protected. When you navigate to any of them without being logged in, you are redirected to the researcher login page. Enter the username and password you set in step 2 of the wizard to gain access. The session lasts 8 hours; after that you will be asked to log in again.

### 5. Configure the study in the Configurator

The Configurator (`/configurator/`) is the central control panel for your study. It determines what data is collected and when participants are asked questions — for both Android and iOS devices. Open it, log in with your researcher credentials, and work through its four pages.

---

**Page 1 — Study Information**

Fill in the basic details that participants see when they join the study:

- **Study title** — displayed in the AWARE app after joining
- **Study description** — explains the study purpose to participants
- **Researcher's first and last name**
- **Researcher's contact email** — participants can use this to reach you

All five fields are required before you can proceed.

---

**Page 2 — Study Questions (ESM)**

ESM stands for Experience Sampling Method — timed in-app questionnaires pushed to participants' phones. Add as many questions as you need; each question can be independently configured.

Each question requires:

- **Type** — choose from: Free Text, Single Choice (radio), Multiple Choice (checkbox), Likert Scale, Quick Answer, Scale, or Numeric
- **Title** — the question text shown to the participant
- **Submit button label** — defaults to "Submit"
- **Answer options** — for choice-based types, add one option per line

Questions can be reordered and deleted. They are only sent to participants when assigned to a schedule (next page).

---

**Page 3 — Schedule Configuration**

Schedules control when ESM questions are delivered. Add one or more schedules and configure each one:

- **Hours** — tick the hours of the day when questions should be triggered (e.g. 09:00, 12:00, 18:00). At each selected hour the app will show the assigned questions.
- **Questions** — select which questions from page 2 belong to this schedule. Each schedule can contain any subset of questions.

Multiple schedules can run in parallel with different questions and different delivery times.

---

**Page 4 — Sensors**

This is the most detailed page. It controls which device sensors are active during the study and how they behave. Changes here affect both Android and iOS participants.

**Upload settings** (apply to all sensors on all platforms):

| Setting                 | Description                                                                               |
| ----------------------- | ----------------------------------------------------------------------------------------- |
| Wi-Fi only              | Upload data only when connected to Wi-Fi                                                  |
| Charging only           | Upload only while the device is charging                                                  |
| Offload frequency       | How often to sync data to the server (minutes)                                            |
| Clean data frequency    | How often to delete already-synced local data (Never / Monthly / Weekly / Daily / Always) |
| Fallback network        | Hours of failed Wi-Fi sync before falling back to mobile data                             |
| Config update frequency | How often the app checks for study config changes (minutes)                               |
| Silent                  | Suppress sync notifications on the device                                                 |
| Foreground priority     | Keep AWARE running continuously as a foreground service                                   |

**Shared sensors** (available on both Android and iOS):

Battery, Screen, Timezone, Accelerometer, Barometer, Bluetooth, Communication (calls), Gyroscope, Linear Accelerometer, Locations (GPS + network), Magnetometer, Network, Processor, Rotation, Significant Motion, Wi-Fi.

Each sensor can be toggled on or off individually. Many expose additional sub-settings when enabled — for example:

- **Accelerometer / Gyroscope / Barometer / etc.** — sampling frequency (in microseconds) and a change threshold to reduce noise
- **Locations** — separate GPS and network provider toggles, frequency, and minimum accuracy in metres
- **Bluetooth / Wi-Fi** — scan frequency in seconds
- **Communication** — Android-only sub-sensors for message logging and communication events

**Android-only sensors**: Gravity, Light, Proximity, Temperature, Applications (with sub-options: notifications, crashes, keyboard logging, on-screen text tracking, app package filter), App Installations, Telephony, MQTT, Screenshot (interval, compression, app filter), Taking Note.

**iOS-only sensors**: Activity Recognition, Contacts sync, Fitbit (steps, heart rate, sleep — requires API key), Google Login, Conversation detection, Fused Location, Device Usage, Calendar, Google Calendar ESM Scheduler, Headphone Motion, HealthKit (sync frequency + historical pre-period), Heart Rate via BLE, NTP clock offset, Pedometer, Push Notification.

**Shared plugins** (Android and iOS):

| Plugin        | Key settings                                                                    |
| ------------- | ------------------------------------------------------------------------------- |
| ESM Scheduler | Enables the question/schedule system from pages 2–3                             |
| Ambient Noise | Sampling frequency (minutes), sample duration (seconds), silence threshold (dB) |
| OpenWeather   | Update frequency (minutes), API key, metric or imperial units                   |

---

**Page 5 — Overview**

Shows a summary of the complete study configuration. When everything looks correct, click **Download Study Config** to save the file. The configuration is written to `studies/` and immediately served at `/studies/` for participants to use.

---

> **Config changes reach participants when their app next syncs.**
>
> Every time you change anything in the Configurator and download a new study config, participants pick the changes up the next time they sync or upload their data — the same action described under [Client apps](#client-apps). There is no separate update step for them to remember.

### 6. Browse collected data in the Analytics Dashboard

The Analytics Dashboard (`/dashboard/`) is the researcher's main window into the collected sensor data. It has two main views — **Overview** and **Per Device** — plus a **Manifest** page.

---

**Overview** (`/dashboard/`)

The default view gives a cross-device snapshot of the entire dataset.

- **Last upload banner** — shows the date and a live "X ago" label (refreshed every 10 seconds) of the most recent data upload across all enrolled devices. If no data has arrived yet it shows "No uploads yet".
- **Export all** button — downloads a single ZIP file containing all sensor data as CSVs, across all devices and both platforms, for offline analysis.
- **Manifest** button — opens the Manifest page (see below).
- **Sensor cards grid** — one card per sensor type, organised into three sections: Shared (available on both platforms), Android only, and iPhone only. Each card shows the record count for Android and iOS and a small visual indicator of the data. Sensors with no data are shown in a muted style.
- **"Only sensors with records" toggle** — hides sensor cards that have received no data yet, letting you focus on what's actually been collected. The preference is saved in the browser and persists across sessions and page refreshes.
- The entire page **updates itself as data arrives**, without any user action. The
  API watches the databases on one shared loop and pushes a message over a WebSocket
  when new rows land, so the counts follow the study rather than a timer. A slower
  poll — five minutes — runs alongside it as a safety net, dropping back to every 60
  seconds if the connection is lost.

---

**Per Device** (`/dashboard/devices/`)

Drill down into an individual participant's data.

- **Device list** (left sidebar) — every enrolled device across both platforms is listed, showing the platform label (Android / iOS), device name (manufacturer + model for Android; label or model for iOS), truncated device ID, and time since the last upload.
- **Click any device** to load it. The URL updates so you can bookmark or share a direct link to a specific device (`/dashboard/devices/android/<id>` or `/dashboard/devices/ios/<id>`).
- **Device info panel** — shows device ID, last seen time, number of active sensors, total record count, and the field values from the most recent upload payload.
- **ZIP export** button — downloads all sensor CSVs for that device in one archive.
- **Sensor cards** — the same sensor card grid as the Overview, but scoped to this device only. Cards are split into Shared and platform-specific sections. Each card has its own individual CSV export button.
- The **"Only sensors with records" toggle** is shared with the Overview page.
- Data **updates as that phone uploads**, over the same live channel as the
  Overview. A device page ignores arrivals belonging to other phones, so it stays
  still while someone else's data comes in.

---

**Manifest** (`/dashboard/manifest`)

A research-grade inventory of the complete dataset — useful for understanding what has been collected before exporting or archiving.

- **Summary stats** at the top: Android device count, iOS device count, total record count across all sensors, and the overall study date span (date of first sample to date of last sample).
- **Per-platform breakdown** — for each sensor on Android and iOS, a row shows:
  - Total record count
  - Number of devices that have contributed data for that sensor / total device count
  - Date of the first sample
  - Date of the last sample
  - Number of database fields, expandable to show the full field name list
- Sensors are **sorted by record count** (most data first). Sensors with no data are listed dimmed at the bottom.
- **Download JSON** button — exports the full manifest as a structured JSON file, useful for archiving dataset metadata alongside the raw CSVs.

## Sensor support

The table below lists every sensor the dashboard can display, as configured in the Analytics Dashboard. For full documentation on each sensor visit the [official AWARE sensor reference](https://awareframework.com/sensors/).

| Sensor                    | Android | iOS | Unit  |
| ------------------------- | :-----: | :-: | ----- |
| Accelerometer             |    ✓    |  ✓  | g     |
| Ambient Noise             |    ✓    |  ✓  | dB    |
| Barometer                 |    ✓    |  ✓  | hPa   |
| Battery Level             |    ✓    |  ✓  | %     |
| Battery Charges           |    ✓    |  ✓  | event |
| Battery Discharges        |    ✓    |  ✓  | event |
| Bluetooth RSSI            |    ✓    |  ✓  | dBm   |
| Calls                     |    ✓    |  ✓  | event |
| Gyroscope                 |    ✓    |  ✓  | rad/s |
| Linear Accelerometer      |    ✓    |  ✓  | g     |
| Location                  |    ✓    |  ✓  | m/s   |
| Magnetometer              |    ✓    |  ✓  | μT    |
| Network                   |    ✓    |  ✓  | event |
| OpenWeather               |    ✓    |  ✓  | °C    |
| Processor                 |    ✓    |  ✓  | %     |
| Rotation                  |    ✓    |  ✓  | rad/s |
| Screen Status             |    ✓    |  ✓  |       |
| Significant Motion        |    ✓    |  ✓  |       |
| Timezone                  |    ✓    |  ✓  | event |
| ESM/EMA                   |    ✓    |  ✓  | event |
| WiFi                      |    ✓    |  ✓  |       |
| Application Crashes       |    ✓    |  —  | event |
| Application History       |    ✓    |  —  | event |
| Application Notifications |    ✓    |  —  | event |
| Applications              |    ✓    |  —  | event |
| Gravity                   |    ✓    |  —  | g     |
| Installations             |    ✓    |  —  | event |
| Keyboard                  |    ✓    |  —  | event |
| Light                     |    ✓    |  —  | lux   |
| Messages                  |    ✓    |  —  | event |
| Network Traffic           |    ✓    |  —  | bytes |
| Notes                     |    ✓    |  —  | event |
| Proximity                 |    ✓    |  —  |       |
| Screen Text               |    ✓    |  —  | event |
| Telephony                 |    ✓    |  —  | event |
| Temperature               |    ✓    |  —  | °C    |
| Touch                     |    ✓    |  —  | event |
| Activity Recognition      |    —    |  ✓  | event |
| Calendar                  |    —    |  ✓  | event |
| Contacts                  |    —    |  ✓  | event |
| Conversation              |    —    |  ✓  | event |
| Device Usage              |    —    |  ✓  | event |
| ESM Scheduler             |    —    |  ✓  | event |
| Fitbit                    |    —    |  ✓  | event |
| Fitbit Data               |    —    |  ✓  |       |
| Fitbit Device             |    —    |  ✓  | event |
| Fused Location            |    —    |  ✓  | m     |
| Google Calendar ESM       |    —    |  ✓  | event |
| Headphone Motion          |    —    |  ✓  | m/s²  |
| Heart Rate (BLE)          |    —    |  ✓  | bpm   |
| HealthKit                 |    —    |  ✓  |       |
| HealthKit Category        |    —    |  ✓  | event |
| HealthKit Quantity        |    —    |  ✓  |       |
| HealthKit Workout         |    —    |  ✓  | event |
| Location Visit            |    —    |  ✓  | event |
| Memory                    |    —    |  ✓  |       |
| NTP                       |    —    |  ✓  | ms    |
| Pedometer                 |    —    |  ✓  | steps |
| Push Notification         |    —    |  ✓  | event |
