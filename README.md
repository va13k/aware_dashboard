# AWARE Dashboard

A self-hosted research platform for collecting and visualising sensor data from Android and iOS devices. The entire stack is bundled into a single Docker Compose project that you can deploy with one command.

## Where to look

This file takes a researcher from an empty machine to a running study, in three
parts and nine numbered steps. It assumes no command-line experience. Anything
that only matters in one situation, such as a database of your own or a server you
are not sitting at, is linked from the step where it comes up rather than standing
in the way of it.

| You are                                                | Read                                                                                                                                                                            |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A researcher setting this up**                       | This file, in order: [Before you start](#before-you-start), then [Deploying it](#deploying-it) (steps 1–5), then [Running a study](#running-a-study) (steps 6–9)                |
| **A researcher whose deployment is misbehaving**       | [When something is wrong](#when-something-is-wrong) — what the deployment tells you about itself, and how to read it                                                            |
| **A researcher using a database of their own**         | [Using a database of your own](docs/guide/own-database.md) — what the wizard asks, what to arrange with its administrator, how to check it                                      |
| **A researcher backing up or restoring a study** | [Backing up and restoring](#backing-up-and-restoring) — what the file carries, what it leaves out, and what the two import modes each do |
| **A researcher keeping a deployment running**          | [Maintenance](docs/guide/maintenance.md) — the operations run by hand rather than by setup                                                                                      |
| **A researcher wondering which sensors are available** | [Sensor support](#sensor-support)                                                                                                                                               |
| **A developer reading the stack for the first time**   | [docs/dev/architecture.md](docs/dev/architecture.md) — what runs, how a request is routed, where a sensor row comes from, and every generated file with its reader              |
| **A developer changing how a deployment is built**     | [docs/dev/deploy-pipeline.md](docs/dev/deploy-pipeline.md) — what `./setup.sh` does, step by step, and what is still done by hand                                               |
| **A developer running the checks**                     | [docs/dev/checks.md](docs/dev/checks.md) — the eight CI jobs and their local equivalents                                                                                        |
| **A developer working inside one component**           | Its own README, beside its code: [analytics_api](analytics_api/README.md), [dashboard](dashboard/README.md), [setup](setup/README.md), [shared_config](shared_config/README.md) |

## What it is

Study participants install the **AWARE client app** on their phone (Android or iOS). The app continuously collects sensor data — accelerometer, GPS, screen events, ambient noise, and [many more](#sensor-support) — and uploads it on the schedule the study configuration sets, so it reaches the analytics dashboard on its own and is ready for browsing, filtering and export. How often that happens, and whether an upload waits for Wi-Fi or for a charger, are yours to set on the Configurator's [Sensors page](#6-configure-the-study-in-the-configurator).

The full stack comprises seven services, running as eleven containers —
[docs/dev/architecture.md](docs/dev/architecture.md) lists every one of them:

| Service                                                                        | Role                                                                                                                                                                                                                   |
| ------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Nginx**                                                                      | Reverse proxy — routes all public traffic, terminates TLS, enforces authentication                                                                                                                                     |
| **Analytics API**                                                              | FastAPI backend for the dashboard — queries the database and serves sensor data and exports                                                                                                                            |
| **Analytics Dashboard**                                                        | React frontend — visualises collected data per device and sensor; exports CSVs and ZIPs                                                                                                                                |
| [**AWARE Configurator**](https://github.com/awareframework/AWARE-Configurator) | Django + React app for building and publishing study configurations for Android and iOS                                                                                                                                |
| [**AWARE Micro Server**](https://github.com/awareframework/aware-micro-server) | Kotlin / Vert.x server that receives data uploads and writes them to MySQL. One instance serves iOS; a second serves Android whenever the study sends its data through the server rather than straight to the database |
| **MySQL + backup**                                                             | Shared database for all collected data, with a configurable automated backup job                                                                                                                                       |
| **Message broker**                                                             | Mosquitto — carries what you send to a participant's phone: a request to sync, a question, a notice. See [Reach a participant's phone](#8-reach-a-participants-phone)                                                  |

A browser-based **setup wizard** is included for the initial deployment — it writes your configuration and launches the stack without any manual file editing.

### Client apps

Study participants need the AWARE client app installed on their device. These are the two builds this deployment is written against, and the same links the study's own join page hands to participants:

| Platform    | What the participant installs                                                                                                              | Source                                                                        |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------- |
| **Android** | [aware-phone-release.apk](https://github.com/va13k/aware-client/releases/download/4.8.2.beta/aware-phone-release.apk) — release 4.8.2.beta | [va13k/aware-client](https://github.com/va13k/aware-client)                   |
| **iOS**     | [AWARE Client v2 on the App Store](https://apps.apple.com/ch/app/aware-client-v2/id1455986181)                                             | [tetujin/aware-client-ios-v2](https://github.com/tetujin/aware-client-ios-v2) |

The Android client is installed from that APK rather than from Google Play, so the phone asks the participant once to allow it. The App Store link opens in whichever storefront the participant's own Apple account uses.

Once a participant joins a study — by scanning the QR code or opening the study link — the app begins collecting, and uploads on the schedule the study configuration sets.

## Before you start

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

Treat the wizard URL as a credential while it is up. The page behind that token holds this deployment's database password and the researcher's own, and it is served over plain HTTP, so the token is what stands between them and anyone who can reach port `9999`. `setup.sh` removes the wizard container when setup finishes. On a network you do not trust, set `SETUP_BIND=127.0.0.1` in `.env` before running setup and reach the wizard through an SSH tunnel instead — see [Remote server deployment](#deploying-on-a-remote-server).

### SSL certificate (optional, recommended for remote servers)

If you want HTTPS, obtain a certificate for your domain before running setup — for example with [Let's Encrypt / Certbot](https://certbot.eff.org/). The setup wizard will ask for the paths to the certificate and private key files.

### Where the study database will run

Setup asks this while you are filling in the form, and there are two answers:

| Choice               | What it means for you                                                                                                                                                                                                                           |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **On this machine**  | The deployment brings up its own database, creates everything inside it and manages its accounts. Nothing has to exist beforehand and nothing here needs arranging — this is the answer to take unless you have a reason to take the other one. |
| **Somewhere I name** | A database you give it: your own server, your institution's, or one you rent from a provider. The deployment starts none of its own.                                                                                                            |

If you are taking the second, read [Using a database of your own](docs/guide/own-database.md)
before step 3. It covers what the wizard asks you for, what to arrange with whoever
administers the server, and how to check the connection before a study depends on it.

## Deploying it

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
4. **Tries to open the URL in your browser** automatically (macOS and Linux with a desktop). On a headless server, this step does nothing — see [Remote server deployment](#deploying-on-a-remote-server) below.

Once the setup page opens in your browser — either automatically or after you copied the URL from the terminal — you are ready to continue. **Proceed to [Step 3 — Complete the setup wizard](#4-complete-the-setup-wizard).**

#### Re-running setup

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

### 4. Complete the setup wizard

The wizard has five steps. A progress bar at the top tracks where you are. You can go back to any previous step before deploying.

---

**Step 1 — Database**

Set the **database administrator** and its password. This is the account that creates the schemas, this study's own accounts and its tables.

On a database you name, both are required and both come from your provider: `avnadmin` on Aiven, `doadmin` on DigitalOcean.

On the database deployed here, both are an offer rather than a question. Leave them blank and the deployment administers its own server with the password it generated for it. Name an administrator instead and setup creates that account with the password beside it. The wizard refuses two answers, because neither can be carried out: `root`, which is that database's own account and already holds a password nobody typed, and half a pair, since no account can be created from a name without a password or a password without a name.

Set the **participant device password** as well. This is the password of the MySQL account that participant devices use to insert their data, and it is the password participants type on their phone when the study configuration is served without an embedded password (the **Configure without password** option in the Configurator).

- Use the **Generate** button to create a random one, or type your own — letters, digits and `. _ ~ @ # % ^ * + = : -` are allowed.
- Leave it blank to keep the password the deployment already uses, or to have one generated on a fresh install.
- On a re-run, the field is pre-filled with the current password. Changing it here applies the new password to the MySQL accounts on the next deployment, so any device still holding the old one must be given the new password.
- The wizard shows the password again on the completion screen, and it is stored as `PARTICIPANT_DB_PASSWORD` in `.env`. You can also set it there before running `setup.sh`.

This password belongs to the account a phone opens the database with, which is what the **straight to the database** dataflow asks of a phone. On the **through the server** dataflow no phone opens MySQL at all: the micro-server performs every write, with an account of its own — `aware_android_server` — and its own password, generated into `ANDROID_SERVER_DB_PASSWORD`. Nothing publishes that one, and the Configurator's Database access step edits whichever of the two the study's dataflow puts on the ingest path, naming the account it is changing.

The two accounts are granted different things, because they do different work:

| Account                     | Granted                                                                                                          | Used by                                                         |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| `aware_android_participant` | `INSERT` on the Android schema                                                                                   | A participant's phone, on the straight-to-the-database dataflow |
| `aware_android_server`      | `INSERT` on the Android schema, plus reading `device_enrolment`, keeping `refusals`, and updating `aware_device` | The Android micro-server, on the through-the-server dataflow    |
| `aware_analytics`           | `SELECT` on both schemas, with write on the dashboard's own cache tables                                         | The dashboard's API and its refresher                           |

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

**Use detected local IP** _(default)_

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

| Provider                                                                              | Notes                                    |
| ------------------------------------------------------------------------------------- | ---------------------------------------- |
| [DigitalOcean Droplet](https://www.digitalocean.com/products/droplets)                | Simple, affordable, good starting point  |
| [Hetzner Cloud](https://www.hetzner.com/cloud/)                                       | Very affordable European option          |
| [AWS EC2](https://aws.amazon.com/ec2/)                                                | Widely used, more configuration required |
| [Google Cloud Compute Engine](https://cloud.google.com/compute)                       | Similar to AWS                           |
| [Azure Virtual Machines](https://azure.microsoft.com/en-us/products/virtual-machines) | Microsoft's offering                     |

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

### 5. What you can access

Once deployment is complete, open the main page at `http://your-host/` (or `https://` if you enabled TLS).

The main page links to all four sections of the platform:

| Page                    | URL              | Access                     |
| ----------------------- | ---------------- | -------------------------- |
| **Join the study**      | `/studies/`      | Public — no login required |
| **Configurator**        | `/configurator/` | Researcher login required  |
| **Analytics Dashboard** | `/dashboard/`    | Researcher login required  |
| **Backup & Restore**    | `/backup/`       | Researcher login required. See [Backing up and restoring](#backing-up-and-restoring) |

**Join the study** is intentionally public so that participants can reach it without credentials. It asks which phone they have and then shows only that platform's steps: where to get the app, the join URL to copy, and the QR code to scan. The page guesses the platform from the browser and lets them switch.

All other pages are protected. When you navigate to any of them without being logged in, you are redirected to the researcher login page. Enter the username and password you set in step 2 of the wizard to gain access. The session lasts 8 hours; after that you will be asked to log in again.

### Checking the ingest path before anyone enrols

Setup runs `setup/verify_ingest.py` once the containers report healthy, and both the
terminal and the wizard page show what it found. It asks the deployment the question a
participant's phone will ask, at the study's public address rather than over the
compose network:

| Check              | What it answers                                                                               |
| ------------------ | --------------------------------------------------------------------------------------------- |
| Endpoint reachable | The address the study hands out answers, with the configuration a joining phone reads         |
| Certificate        | On HTTPS, the certificate that address presents verifies, and when it expires                 |
| Test record lands  | A row posted the way the client posts one is admitted and is in the study database afterwards |
| Probe removed      | Everything the check wrote has been taken back out                                            |

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

### Deploying on a remote server

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

## Running a study

The deployment is up and a participant can join it. What follows is the study
itself: telling the app what to collect, watching what arrives, reaching a
participant, and recording that one has left.

### 6. Configure the study in the Configurator

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

#### How a change reaches a participant's phone

A change is not in force when you download it. It is in force once each phone has
read it, and that happens in three ways.

**On its own, on a schedule.** The app re-reads the configuration every
**Config update frequency** minutes, which you set on the Sensors page above. This
is its own timer, separate from **Offload frequency**, so a phone picks up a changed
study without waiting to upload anything. Nothing is asked of anybody, and for most
changes this is the path to rely on.

**Because you asked.** Send **Ask the phone for a study update** from
[Reach a participant's phone](#8-reach-a-participants-phone) and the phone re-reads
now instead of waiting on that timer. Worth it for a change you need in place before
the next session.

**Because the participant asked.** A participant can force it from the app, which is
what to tell someone you have on the phone.

- **Android** — in the app, tap **CHECK FOR STUDY UPDATES**.

  ![The CHECK FOR STUDY UPDATES button in the Android app](docs/images/android-check-study-updates.png)

- **iPhone** — on the app's Settings screen, tap the refresh button at the top right.

  ![The refresh button in the iPhone app](docs/images/ios-update-button.png)

Whichever way it happened, you do not have to take it on trust: a device's page in
the dashboard carries a badge saying whether that phone's configuration
**matches** the deployed one, **differs** from it, with a count of the fields and
what they are, or is **unknown** because the phone has not reported one yet.

### 7. Browse collected data in the Analytics Dashboard

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

---

**Client Logs** (`/dashboard/logs`)

The lines each client writes about its own operation — what it started, what it could not do, what it retried. This is where to look when a phone is collecting less than you expected and the reason is on the phone rather than on the server.

- **Android / iPhone toggle** at the top right — the two platforms record their logs differently, so they are read separately.
- **Filter by type, by time window, or by text**, and download the filtered set.
- **Refused writes** — when the server turned data away, a line per device says which device, why, how many attempts it made and how many rows were refused.

---

**Messages** (`/dashboard/messages`)

Where you send something to a participant's phone and see what came of it. Described in full in [Reach a participant's phone](#8-reach-a-participants-phone) below.

### 8. Reach a participant's phone

Everything else in this stack observes. This is the one part that speaks: you can ask a phone to upload now, ask the participant a question, or tell them something. Sending happens on **Messages** (`/dashboard/messages`); a single device's page has a **Prompts and answers** view showing what that one participant was asked, what they answered, and how long they took.

> **Android only.** These messages travel over the message broker, and it is the Android client that subscribes to it. An iPhone in the study receives nothing, so on a study running both platforms this cannot be the way you reach everyone.

**What you can send**

| Choose                               | What the participant sees                                    | When to use it                                                                                                                |
| ------------------------------------ | ------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------- |
| **Ask the phone to upload**          | Nothing at all                                               | A phone has gone quiet and you want to know whether it is holding data                                                        |
| **Ask the phone for a study update** | Nothing at all                                               | You changed questions, schedules or sensors, and want the phone to re-read the configuration now rather than on its own timer |
| **Ask a question**                   | A question that waits on the phone until it is answered      | Anything outside the protocol — a check on a quiet phone, a one-off ask                                                       |
| **Ask about this moment (ESM)**      | The same question, expiring if it is not answered in time    | What the study is measuring: an answer given hours later describes a different moment                                         |
| **Tell them something**              | A notification, with the sound and vibration they configured | A thank-you, a reminder, an announcement. No answer is asked for and none is recorded                                         |

A question can offer a few one-touch answers, or leave the participant a free-text box.

**What became of it, in three separate columns**

| Column        | Means                                                                                 |
| ------------- | ------------------------------------------------------------------------------------- |
| **Sent**      | This deployment published it. Ours to know, and known at once                         |
| **Delivered** | The phone reported receiving it, in a row it uploaded along with the rest of its data |
| **Answered**  | The participant tapped an answer                                                      |

**Delivered lags a sync, and that is a normal state rather than a failure.** The phone writes every message it receives into a table of its own, and that table reaches you only when the phone next uploads. So a message to a quiet phone reads as undelivered until then — which is exactly why **Ask the phone to upload** exists.

**Limits, deliberately**

One device may be sent **6 prompts an hour** — questions and notices — and **30 upload or update requests an hour**, which cost the participant nothing and show them nothing. Past the limit the dashboard tells you what the limit is and when it lifts, rather than refusing silently. A participant's phone is not a channel to keep pushing at.

**Whether the wording is kept**

Composing a message ends in two buttons: **Keep and send**, and **Send without keeping**. Either way a row is written saying that you sent something, to whom and when — a channel to participants that leaves no trace is not one a study should have. What the second button leaves out is the words themselves.

**From a terminal instead**

The same five things, for anyone who prefers the command line. On macOS and Linux the `--docker-prefix sudo` is what lets it reach the broker container:

```bash
python3 setup/send_message.py --docker-prefix sudo devices
python3 setup/send_message.py --docker-prefix sudo sync --device all
python3 setup/send_message.py --docker-prefix sudo ask --device <id> --title "How are you?" --instructions "One touch answer" --answers Good,Fine,Bad
python3 setup/send_message.py --docker-prefix sudo notice --device <id> --title "Thank you" --instructions "The study finishes on Friday."
python3 setup/send_message.py --docker-prefix sudo history --device <id>
```

`history` reads what the phones reported, so it shows what was delivered and what was answered — the same three states the Messages page keeps apart.

### 9. When a participant leaves the study

Two different actions, and they are kept apart deliberately: consent forms answer
their two questions differently, so folding them into one button would answer one of
them on your behalf.

|              | **Withdrawal**                                           | **Exclusion**                                  |
| ------------ | -------------------------------------------------------- | ---------------------------------------------- |
| Answers      | _When was this participant in the study?_                | _Is their data part of the analysis?_          |
| Changes      | What the coverage grid expects, and how the device reads | What the exports and the coverage grid contain |
| Platforms    | Android only                                             | Android and iOS                                |
| Reversible   | Yes — **Rejoin** reopens the window                      | Yes — putting them back removes the exclusion  |
| Deletes data | No                                                       | No                                             |

**Withdrawal — recording that they left.** On the device's page. You can give the
date they actually left rather than today's, because a researcher usually finds out
by being told rather than by watching a phone go quiet. From that moment the
coverage grid stops expecting data, and the device reads as _withdrawn_ instead of
merely gone silent.

> **It does not stop the phone.** The phone is told nothing, keeps collecting, and
> keeps uploading; rows that arrive after the window closes are still stored. The
> rule at ingest admits any device that ever joined the study and does not ask
> whether its window is open — a device that left keeps the data it had not managed
> to upload yet, which is data the study could not collect again. Collection stops
> when the participant leaves the study in the app or removes it from their phone.

Withdrawal is Android only. An iPhone keeps its study state on the phone and never
uploads it, so the server holds no window to close.

**Exclusion — taking their data out of the analysis.** Also on the device's page,
and on either platform. The rows stay in the database and the device stays on screen
marked as excluded: a participant the dashboard had quietly dropped would be
indistinguishable from one who never took part. What changes is the exports and the
coverage grid — the exports because that is where the analysis dataset actually
leaves.

**Neither one deletes anything.** The dashboard reads study data and has no
privilege to remove it. If consent requires the rows to be gone, that is a request
to whoever administers the database — and it is worth agreeing on the wording of
that request before a study starts rather than after somebody withdraws.

The default is the conservative reading: withdrawal keeps what was collected, and a
device is excluded only because somebody said so.

## Backing up and restoring

**Backup & Restore** (`/backup/`) takes the study's two databases out as one
compressed file, and reads one back in. Both directions run as `aware_backup`, an
account holding everything inside those two schemas and nothing at all outside them,
because a restore feeds a file into a database client and every statement in that
file runs.

Nothing is staged on disk in either direction. An export compresses straight into
the download and an import decompresses as it reads, so a database of a hundred
gigabytes goes through the page without needing room for a copy of itself. Both are
long enough at study scale to be shown as a job with a progress bar rather than a
page that waits.

### Taking a backup

Choose what to include, then **Export**:

| Period | What it means |
| --- | --- |
| **Everything** | Every row both databases hold |
| **Recent data** | A stretch counted back from a point you pick, either the newest data or right now. Counting back from the newest data is the one to take when collection has already stopped |
| **Specific dates** | The first and last day to include |

When the download finishes the page shows the file's **SHA-256 digest**. A streamed
export cannot report its own size in advance, so comparing that digest against the
file you received is how you know it arrived whole. Worth doing before you delete
anything on the strength of having a backup.

### Putting one back

Point the page at a file, either one **already on the server** from the nightly
archive or one you **upload** from your own computer, and choose what should happen
to the rows. Uploading is practical up to a few gigabytes; past that, put the file on
the server and pick it there.

The picker also offers **Download this backup**, which takes an archive off the
server. That is what you want when the server itself is the thing you are leaving.

**Add data** folds the file into what is already stored:

- Every table the file names keeps the rows the database already has.
- A row is admitted when its timestamp is later than the newest one that phone
  already has in that table. Anything at or before that counts as stored and is left
  out, so this does not fill in gaps behind what a phone has already delivered. A
  phone with nothing stored here keeps every row the file offers for it.
- Re-reading the same backup a second time adds nothing.
- Rows arrive with new identifiers, since the `_id` a row carried belongs to the
  deployment that wrote it.

**Replace everything** runs the file as written. Every table the file contains is
dropped and rebuilt from it. Tables the file does not contain are left exactly as
they are, which matters more than it sounds and is the subject of the next section.

Either way, the record counts and the coverage grid are rebuilt afterwards from what
is actually stored, so the figures on screen describe the database you now have.

### What a backup does not carry

The file holds the study's data. It does not hold the tables the dashboard derives
from that data, because each of those summarises the row identifiers of the
deployment that built it, and a summary restored from elsewhere describes rows the
target does not have. Those are rebuilt on import instead.

Two of the tables left out are not summaries. They are decisions:

| Left out of the file | What it holds | What that means |
| --- | --- | --- |
| `device_enrolment` | When each phone was in the study, including **withdrawals and rejoins you entered by hand** | A restore rebuilds this from the phones' own study logs. A hand-entered withdrawal is not in those logs, and **Replace everything** clears the table deliberately, since windows a researcher entered describe participants the restored database may not hold |
| `device_exclusions` | The participants you took out of the analysis | Not in a file you download from the page. It survives a restore onto the same deployment, because a table the file does not contain is not touched, and it does not travel to a different one |

So the practice worth adopting is simple: **keep your own note of who was withdrawn
and who was excluded**, outside the database. Restoring in place leaves exclusions
alone and rebuilds enrolment from the phones. Moving a study to another deployment
carries neither, and both are decisions about people that no amount of data can
reconstruct.

The refusal counters are left out for the same technical reason and accepted as
lost: they describe attempts against one deployment's ingest path.

### The nightly archive

Separately from the page, a scheduled job dumps both databases into a folder on the
host. How often, where, and how long the files are kept are set in the wizard's
backup step, described under
[Complete the setup wizard](#4-complete-the-setup-wizard).

That archive is what the **already on the server** picker offers, and it carries
slightly more than a page export does: the exclusions and the refusal counters are
in it, because it is never a ranged dump and so never has to leave out the tables
that carry no timestamp to range over. Restoring one with **Replace everything**
therefore brings the exclusions back with it.

## When something is wrong

Most problems here answer themselves if you know where to ask, and the deployment
carries four answers of its own. Reach for these before changing anything —
re-running setup fixes a genuinely broken configuration, and tells you nothing about
a phone that has not uploaded yet.

| What you want to know                 | Ask this                                                | It tells you                                                                                                                                                                          |
| ------------------------------------- | ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Is every part running?                | `sudo docker compose ps`                                | One line per container, with `healthy`, `starting`, `unhealthy` or `exited`                                                                                                           |
| Why is that one not running?          | `sudo docker compose logs --tail=50 <service>`          | Its own last words. Service names: `nginx`, `mysql`, `micro-server`, `micro-server-android`, `dashboard-api`, `dashboard`, `configurator`, `mqtt`, `counts-refresher`, `mysql-backup` |
| Can this study use its database?      | `python3 setup/verify_database.py --docker-prefix sudo` | Five checks with a mark each, and a hint naming the likely cause                                                                                                                      |
| Would a phone's data actually arrive? | `python3 setup/verify_ingest.py --docker-prefix sudo`   | Walks the phone's own path from outside the deployment and posts a real test row                                                                                                      |
| Are the ports it needs free?          | `python3 setup/check_ports.py --docker-prefix sudo`     | Each address a container publishes, and for a port that is taken, what holds it                                                                                                       |

On Windows leave `--docker-prefix sudo` off. Both are safe to run on a live study.
The database check only ever asks questions. The ingest test posts one row from a
synthetic device named for that run, then removes it along with everything keyed to
that name, and reports the cleanup as part of its own result — so a failed run does
not leave a probe behind in your data.

**Reading a check report.** Each line carries one of four marks, and telling them
apart is most of the work:

| Mark   | Means                                                                                                                                                    |
| ------ | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ok`   | Asked and answered                                                                                                                                       |
| `warn` | Not there, and setup will create it on the next deploy. Before a first deployment this is the normal reading for the schema, the accounts and the tables |
| `FAIL` | Something you have to fix. The study cannot collect until you do                                                                                         |
| `skip` | Not asked, because an earlier answer made it meaningless                                                                                                 |

---

#### Setup will not finish

| What you see                                                               | What it usually is                                                                                                                                                              | What to do                                                                                                                                                                                                                                                                                                                                                 |
| -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Docker is required but was not found`                                     | Docker Desktop is installed but not started, or not installed                                                                                                                   | Start Docker Desktop and wait for the whale icon to stop animating, then run setup again                                                                                                                                                                                                                                                                   |
| The wizard URL never prints                                                | The wizard container did not start                                                                                                                                              | `sudo docker compose logs setup-wizard`                                                                                                                                                                                                                                                                                                                    |
| The wizard URL prints but the page does not open                           | You are deploying a server you are not sitting at, and port `9999` is not reachable from your machine                                                                           | Put `SETUP_BIND=127.0.0.1` in `.env` and reach it through an SSH tunnel — see [Remote server deployment](#deploying-on-a-remote-server)                                                                                                                                                                                                                    |
| `Cannot read .env — it is owned by another user (root?)`                   | An earlier run was made with `sudo` and left the file owned by root                                                                                                             | `sudo chown $USER .env`, then run setup again                                                                                                                                                                                                                                                                                                              |
| `These ports are already in use, and this deployment has to publish them:` | Another program on this machine is serving a port the stack needs — a system Apache or Nginx on 80, a local MySQL on 3306, a local Mosquitto on 1883, or another Docker project | The report names each port, what needs it, which of this machine's addresses answered, and what holds it. When a Docker container holds it, it gives you the `docker stop` command; otherwise it gives you the command to find the program. Free the port and run setup again — these addresses are fixed, so the stack has no second port to fall back on |

#### A container will not become healthy

Start with `sudo docker compose ps` to see which one, then read its logs. The
common ones:

- **`mysql` is `starting` for a few minutes on a first deploy.** It is creating the
  schema, which is a large file. It is given up to five minutes before it counts as
  failed; wait before concluding anything.
- **`nginx` exits immediately.** It refuses to start rather than serve a study
  config unguarded, so a missing generated file stops it. Re-running setup writes
  those files again.
- **`micro-server` or `micro-server-android` is `unhealthy`.** Its configuration is
  the usual cause. `sudo docker compose logs micro-server` names what it could not
  read. If a deploy printed _"Not world-readable, so the container that bind-mounts
  it cannot open it"_, that is the same fault caught earlier.
- **Everything is `healthy` and the site still does not answer.** Check the address
  you are using against the one setup printed — the access links are in
  `deployment-urls.json`.

#### The database check fails

The hint on the failing line is usually the whole answer. What each one means:

| The detail says                          | What it is                                                                                                                                                                                                                                                                                                                                                                              |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| The name does not resolve                | A typo in the host. It wants the host on its own — no scheme, no account, no database name                                                                                                                                                                                                                                                                                              |
| The name resolves and nothing answered   | Either the wrong port, or the provider refusing this machine. Managed databases rarely use `3306`: Aiven and DigitalOcean give each database its own port, printed beside the host in their console. If the port is right, add this machine's address to the provider's allowed list — _Allowed IP addresses_, _Trusted sources_ or _Authorized networks_ depending on who you are with |
| An account will not authenticate         | The password in `.env` and the one on the server have drifted apart. Run `./setup.sh` and choose _Deploy with current config_, which re-applies them. Starting the containers with `docker compose up` on its own does not — it leaves the existing database untouched                                                                                                                  |
| Encryption was asked for and not offered | The server cannot do TLS. Either enable it there, or say so for this study — see [Encryption to the database](docs/guide/own-database.md#encryption-to-the-database-and-who-decides-it)is right, add this machine's address to the provider's allowed list — _Allowed IP addresses_, _Trusted sources_ or _Authorized networks_ depending on who you are with                           |
| An account will not authenticate         | The password in `.env` and the one on the server have drifted apart. Run `./setup.sh` and choose _Deploy with current config_, which re-applies them. Starting the containers with `docker compose up` on its own does not — it leaves the existing database untouched                                                                                                                  |
| Encryption was asked for and not offered | The server cannot do TLS. Either enable it there, or say so for this study — see [Encryption to the database](docs/guide/own-database.md#encryption-to-the-database-and-who-decides-it)                                                                                                                                                                                                 |

When the report ends with _"This database can take this study"_, nothing is wrong:
what is missing is what the deploy creates.

#### The ingest self-test fails

This is the one worth acting on before anyone enrols, because a study that fails it
looks deployed and collects nothing.

- **Endpoint** — the address the study hands out does not answer from outside. Check
  that ports `80` and `443` are open in the server's firewall and at the provider,
  and that the public host setup detected is the one participants can actually reach.
- **Certificate** — the report names who it was issued to and when it expires. A
  name that does not match the address, or a date in the past, is a certificate to
  renew; afterwards run setup again so the new files are picked up.
- **Test record** — the path is reachable but the write did not land. The database
  check above is the next thing to run.

#### Nothing is arriving in the dashboard

Work down this list in order; each step rules out the one before.

1. **Has anyone joined?** Open **Per Device**. An empty list means no phone has ever
   reported in — start from the join page and the QR code rather than from the server.
2. **When did that phone last upload?** The device list carries a last-seen time.
   Phones upload on a schedule, and two settings can hold one back for a long time:
   **Wi-Fi only** and **Charging only**. **Offload frequency** is how often it tries.
   To stop waiting, send **Ask the phone to upload** from
   [Messages](#8-reach-a-participants-phone).
3. **Is the server turning data away?** Open **Client Logs**. A banner at the top
   counts refused writes, with a line per device saying why. _"no enrolment window
   the study log put there"_ means that phone never actually joined this study — it
   has the app and is trying to upload, but the study log holds no join for it.
   Usually it joined a different study URL, or the study's dataflow changed after it
   joined, which requires every participant to join again. _"named no device at all"_
   is a request with no device id, which no properly joined phone sends.
4. **Does the phone read as `Unknown`?** On its page, that badge means no study event
   says whether it is in the study — the same finding as a refusal, seen from the
   other side.
5. **Does the Overview say records have no device id?** That banner counts rows that
   arrived without a device. They are counted and never exported, which is why a
   total can exceed what a download produces. A handful is an early test; a large
   block is worth asking about before anything is discarded.

#### The numbers look wrong rather than missing

- **The phone carries an old configuration.** Its page shows **Config differs** with
  a count, and lists the fields. Send **Ask the phone for a study update** and it
  re-reads now instead of waiting on its own timer, or have the participant force it
  from the app: see
  [How a change reaches a participant's phone](#how-a-change-reaches-a-participants-phone).
- **The coverage grid is emptier than expected.** A cell is judged against what the
  study asked for, so a low count with a strong colour is a sensor that was expected
  and did not arrive — check that sensor is enabled for that platform, and that the
  participant granted the permission it needs.
- **A withdrawn participant's data is still arriving.** That is how it works:
  withdrawal records when they were in the study and does not stop their phone. See
  [When a participant leaves](#9-when-a-participant-leaves-the-study).

#### Messages never show as delivered

Normal until that phone next uploads. **Delivered** is the phone's own report,
carried up with its data, so it lags a sync rather than confirming one. **Sent**
going up while **Delivered** stays put means the phone has not been heard from.

#### I cannot log in

The researcher username and password are in `.env`, as `RESEARCHER_USERNAME` and
`RESEARCHER_PASSWORD`. Open that file to read them rather than deploying again. To
change them, run setup and choose _Edit configuration first_.

A session lasts 8 hours, so being asked to log in again after a working day is
expected rather than a fault.

---

#### When you do ask for help

Send these four things and almost any question can be answered without a call:

```bash
sudo docker compose ps
python3 setup/verify_database.py --docker-prefix sudo
python3 setup/verify_ingest.py --docker-prefix sudo
sudo docker compose logs --tail=50 <the service that looks wrong>
```

**Never send `.env`, `source.json`, or the setup wizard URL.** All three carry this
deployment's passwords. The check reports are written to be shareable — they name
hosts, ports and accounts, never a password. If you need to quote a database host
that arrived as a connection string, remove the account and password from it first.

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
