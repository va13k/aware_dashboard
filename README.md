# AWARE Dashboard

A Docker-based research framework for collecting sensor and survey data from Android and iOS devices. It combines a study configurator, a mobile data server, a shared MySQL database, and an Nginx reverse proxy into a single setup flow.

## Endpoints

The user-facing endpoints are exposed by **Nginx** on ports `80` and `443`.

### User-facing endpoints

| Public path               | Purpose                                                | Backing service                                     |
| ------------------------- | ------------------------------------------------------ | --------------------------------------------------- |
| `/`                       | Main page with links to the available services         | Nginx landing page                                  |
| `/configurator/`          | Android study builder UI                               | Django + React configurator                         |
| `/studies/`               | Studies page with Android files and iOS QR/join access | Generated page served by Nginx                      |
| `/studies/files/`         | Raw Android study JSON file listing                    | Files saved by the configurator and served by Nginx |
| `/:studyNumber/:studyKey` | Join page for a specific iOS study                     | AWARE Micro Server                                  |

### Notes

- Open `http://localhost/` locally, or `http://your-hostname/` on your server, to reach the main page.
- `/studies/` now combines Android study access with the iOS QR/join page.
- `/studies/files/` keeps the raw Android JSON file browser.
- The AWARE iOS client sends `POST` requests to `/index.php/...`; this is an API path, not a standalone user-facing page.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with Compose v2
- [Git](https://git-scm.com/)

## Deployment

### 1. Clone the repository

```bash
git clone https://github.com/va13k/aware_dashboard.git
cd aware_dashboard
```

### 2. Run the one-command setup flow

macOS / Linux:

```bash
./setup.sh
```

Windows:

```bat
setup.bat
```

This opens a setup wizard at `http://localhost:9999`.

When you click **Deploy**, the setup flow will:

1. write `.env`
2. create or update `aware-micro-server/aware-config.json`
3. create or update `studies/studyConfig.json`
4. create or update `studies/index.html`
5. build the Docker images
6. start MySQL, the configurator, the micro-server, and Nginx

The runtime stack in `docker-compose.yml` only contains the long-running services. File generation happens inside `setup.sh` and `setup.bat` before the containers are started.

The intended local prerequisites are only Git and Docker.

### Headless Linux server deployment

If you deploy on a Linux server without a graphical desktop, the setup still works, but the browser step happens from another machine.

Step by step:

1. SSH into the server.
2. Run `./setup.sh`.
3. The script starts the setup wizard on port `9999`.
4. Because the server has no GUI, the automatic browser open may do nothing. That is expected.
5. Open the setup wizard from your own computer using one of these methods:

Option 1: SSH tunnel

```bash
ssh -L 9999:localhost:9999 your-user@your-server
```

Then open `http://localhost:9999` on your local machine.

Option 2: Temporary public access

Temporarily expose port `9999` on the server firewall, open `http://your-server-ip:9999` from your own computer, finish setup, and then close that port again.

Once you click **Deploy** in the wizard, the server-side `./setup.sh` process continues automatically, writes the configuration files, and starts the full stack.

### 3. Adjust the micro-server study config if needed

The setup flow generates `aware-micro-server/aware-config.json` from `aware-micro-server/aware-config.example.json`, using the public host and protocol you entered in the wizard. By default, it writes `server.database_host` as the internal Docker MySQL service name `mysql`, `server.database_user` as `aware_ios_participant`, and `server.external_server_host` from the public URL. It also generates a Django secret key automatically when one is missing.

After deployment, you can edit `aware-micro-server/aware-config.json` to change:

- study metadata
- researcher details
- enabled sensors and plugins
- iOS study key and study number

Changes to `aware-config.json` are reloaded by AWARE Micro automatically.

### Micro-server `server` fields

These fields in `aware-micro-server/aware-config.json` are the ones that matter in this Docker deployment:

- `database_engine`, `database_host`, `database_name`, `database_user`, `database_pwd`, `database_port`: required. The micro-server uses them to connect to MySQL and write iOS study data into `aware_ios`.
- `external_server_host`, `external_server_port`: required for participant-facing study URLs, QR codes, and websocket URLs that the mobile client sees. These should match the public address participants actually use.
- `server_host`, `server_port`, `websocket_port`: required internally. They control which address and ports the micro-server listens on inside the container stack. In this project they should normally stay `0.0.0.0`, `8080`, and `8081`.
- `path_fullchain_pem`, `path_key_pem`: optional here. They are only needed if the micro-server itself terminates TLS. In this setup, Nginx handles HTTPS in front of the micro-server, so these can stay empty.

If your public host and database host are different, you can override the micro-server database target in `.env` with `MICRO_DATABASE_HOST` before redeploying. Public study URLs always come from `PUBLIC_HOST`, `PUBLIC_PORT`, and `PROTOCOL`. If Android clients need a different DB endpoint than `PUBLIC_HOST`, you can also set `ANDROID_DATABASE_HOST`.

### 4. Access the services

| Service                        | URL                                             |
| ------------------------------ | ----------------------------------------------- |
| Main page                      | `http://localhost/` or `http://your-hostname/`  |
| Configurator (Android)         | `http://your-server/configurator/`              |
| Android study files            | `http://your-server/studies/`                   |
| Raw Android study file listing | `http://your-server/studies/files/`             |
| iOS join page                  | `http://your-server/<study_number>/<study_key>` |

## Setting Up A Study

### Android

1. Open the main page at `/`, then choose **Configurator**, or go directly to `/configurator/`.
2. Fill in study info, database connection, sensors, and questions.
3. On the Overview page, click **Download Study Config**.
4. The study file is saved into `studies/` and exposed at `/studies/files/<study-id>.json`.
5. Share that URL with Android participants.

### iOS

1. Open the main page at `/`, then choose **Studies**, or go directly to `/studies/`.
2. Edit `aware-micro-server/aware-config.json` if needed.
3. In the AWARE iOS app, use the QR code shown on `/studies/`, or enter `http://your-server/index.php/<study_number>/<study_key>` manually. The iOS client then communicates with `/index.php/...` using `POST` requests.

## Sensor Support

Not all sensors are available on both platforms. The table below shows what each platform collects.

| Sensor | Android | iOS | Notes |
|---|:---:|:---:|---|
| Accelerometer | ✓ | ✓ | |
| Gyroscope | ✓ | ✓ | |
| Light | ✓ | ✓ | |
| Barometer | ✓ | ✓ | |
| Magnetometer | ✓ | ✓ | |
| Gravity | ✓ | ✓ | |
| Linear accelerometer | ✓ | ✓ | |
| Rotation | ✓ | ✓ | |
| Proximity | ✓ | ✓ | |
| Temperature | ✓ | ✓ | |
| Battery | ✓ | ✓ | |
| Screen | ✓ | ✓ | |
| WiFi | ✓ | ✓ | |
| Bluetooth | ✓ | ✓ | |
| Processor | ✓ | ✓ | |
| Telephony | ✓ | ✓ | |
| Applications | ✓ | ✓ | |
| Timezone | ✓ | ✓ | |
| ESM | ✓ | ✓ | |
| Location | ✓ | ✓ | Android splits into GPS / network / passive; iOS uses a single location sensor |
| Network | ✓ | ✓ | Android splits into events and traffic tables; iOS records reachability events only |
| Calls & messages | ✓ | ✓ | Android exposes `calls` and `messages` separately; iOS bundles them as `communication` |
| Significant motion | — | ✓ | iOS motion coprocessor only |
| Keyboard | ✓ | — | |
| Touch | ✓ | — | |
| Notifications | ✓ | — | |
| Screenshots | ✓ | — | |
| App installations | ✓ | — | |
| Crashes | ✓ | — | |

### Key differences

- **Location** — Android has three separate providers (`status_location_gps`, `status_location_network`, `status_location_passive`). iOS uses one unified location sensor (`locations`).
- **Network** — Android writes connection events to the `network` table and traffic bytes/packets to `network_traffic`. iOS only collects reachability state changes in a single `network` table.
- **Calls and messages** — Android records these in separate tables (`calls`, `messages`). iOS stores both under `communication`.
- **System sensors** — keyboard input, touch events, notifications, screenshots, and app installs are Android-only. iOS restricts access to these at the OS level.

## HTTPS

1. Obtain certificates, for example with Let's Encrypt.
2. Place them in a readable location such as `./certs/fullchain.pem` and `./certs/privkey.pem`.
3. Re-run `./setup.sh` or `setup.bat` and enable HTTPS in the wizard.

Nginx will terminate TLS and redirect HTTP traffic to HTTPS.

## Common Operations

```bash
# View logs
sudo docker compose logs -f
sudo docker compose logs -f configurator
sudo docker compose logs -f micro-server

# Restart one service
sudo docker compose restart configurator

# Stop everything
sudo docker compose down

# Stop and wipe all data (irreversible)
sudo docker compose down -v
```

## Project Structure

```text
aware_dashboard/
|- setup.sh / setup.bat          # One-command setup entry points
|- docker-compose.yml
|- .env                          # Generated by the setup wizard
|- env.example                   # Example environment variables
|- nginx/
|  |- http.conf
|  `- https.conf
|- db/
|  `- create_dbs.sql            # Creates aware_android and aware_ios databases and service users
|- studies/                     # Saved Android study JSON files, served at /studies/
|- AWARE-Configurator/          # Django + React study configurator
|- aware-micro-server/          # Kotlin/Vert.x iOS data server
|  |- aware-config.json         # Generated live server config
|  `- aware-config.example.json # Setup template
`- setup/                       # Setup wizard container
```

## Troubleshooting

**Services take a while to start**

MySQL can take 30-60 seconds to initialize on first run.

```bash
sudo docker compose logs mysql
```

**Cannot reach the server from outside**

Make sure ports `80` and `443` are open in your firewall.

**Configurator shows a blank page after changing domain or protocol**

Rerun `./setup.sh` so the generated files and the configurator build pick up the updated public host and protocol.

The configurator now derives Django allowed hosts from `PUBLIC_HOST`, so `.env` only needs the public host once unless you want to override `DJANGO_ALLOWED_HOSTS` manually.

**iOS data is not appearing in the database**

The `aware_ios_participant` MySQL user must keep `CREATE` and `INSERT` privileges on `aware_ios`.
