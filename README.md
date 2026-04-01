### AWARE Dashboard

# AWARE Dashboard

A Docker-based research framework that combines Android and iOS configuration tools with a shared MySQL database and a unified Nginx reverse proxy.

## Architecture

```
Internet -> Nginx (:80/:443)
              ├── /configurator/*  → AWARE Configurator (Django + React)
              ├── /api/*           → AWARE Micro Server (Vert.x, Kotlin)
              └── /studies/*       → Static JSON study files

           All services → MySQL (:3306, internal only)
```

- **AWARE Configurator** generates study configuration scripts for Android devices.
- **AWARE Micro Server** generates study configuration scripts for iOS devices and handles data collection.
- **MySQL** stores all collected data from both Android and iOS clients.
- **Nginx** serves as the single public entry point, routing traffic to the appropriate service.

## Prerequisites

To deploy the project you will need the following applications:

- [Docker](https://docs.docker.com/get-docker/) (v20.10 or later)
- [Docker Compose](https://docs.docker.com/compose/install/) (v2.0 or later)

## Quick Start

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd aware-dashboard
```

### 2. Create the environment file

Copy the example and edit it with your values:

```bash
cp .env.example .env
```

Open `.env` in a text editor and configure:

```
# MySQL
MYSQL_ROOT_PASSWORD=choose_a_strong_password

# Django (AWARE Configurator)
DJANGO_SECRET_KEY=generate_a_random_string_here
DJANGO_ALLOWED_HOSTS=yourdomain.com,localhost

# Protocol: "http" or "https"
PROTOCOL=http

# SSL certificates (only needed if PROTOCOL=https)
SSL_CERTIFICATE_PATH=./certs/fullchain.pem
SSL_CERTIFICATE_KEY_PATH=./certs/privkey.pem
```

To generate a random Django secret key, you can run:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

### 3. Configure the AWARE Micro Server

Edit `aware-micro-server/aware-config.json` to set your database credentials, study sensors, and plugin settings. Make sure the MySQL credentials match what you set in `.env`.

### 4. Build and start all services

```bash
docker compose up --build -d
```

This will build the Configurator and Micro Server images and start all four containers.

### 5. Verify everything is running

```bash
docker compose ps
```

You should see four containers running: `aware_mysql`, `aware_micro`, `aware_configurator`, and `aware_nginx`.

Once running, the services are available at:

| Service                       | URL                                   |
| ----------------------------- | ------------------------------------- |
| Configurator (Android config) | `http://yourdomain.com/configurator/` |
| Micro Server API (iOS)        | `http://yourdomain.com/api/`          |
| Study JSON files              | `http://yourdomain.com/studies/`      |

## Enabling HTTPS

If your server is publicly accessible and you need encrypted connections:

### 1. Obtain SSL certificates

Use [Let's Encrypt](https://certbot.eff.org/) with Certbot:

```bash
sudo certbot certonly --standalone -d yourdomain.com
```

### 2. Copy certificates to the project

```bash
mkdir -p certs
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem ./certs/
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem ./certs/
sudo chmod 644 ./certs/*.pem
```

### 3. Update the environment file

In your `.env`, change:

```
PROTOCOL=https
SSL_CERTIFICATE_PATH=./certs/fullchain.pem
SSL_CERTIFICATE_KEY_PATH=./certs/privkey.pem
```

### 4. Restart the services

```bash
docker compose down
docker compose up -d
```

Nginx will now redirect all HTTP traffic to HTTPS automatically.

## Live Configuration Changes

The AWARE Micro Server runs in **dynamic mode**. You can edit `aware-micro-server/aware-config.json` at any time and the server will pick up changes automatically without a restart. Connected clients (phones) will retrieve the updated configuration within 15 minutes.

## Common Operations

### View logs

```bash
# All services
docker compose logs -f

# A specific service
docker compose logs -f configurator
docker compose logs -f micro-server
docker compose logs -f mysql
docker compose logs -f nginx
```

### Restart a single service

```bash
docker compose restart configurator
```

### Rebuild after code changes

```bash
docker compose up --build -d
```

### Stop all services

```bash
docker compose down
```

### Stop and remove all data (including the database)

```bash
docker compose down -v
```

> **Warning:** The `-v` flag deletes the MySQL data volume. All collected study data will be lost.

## Troubleshooting

**Services won't start / stay in "waiting" state:**
Check if MySQL is healthy. It can take 30–60 seconds to initialize on first run.

```bash
docker compose logs mysql
```

**Cannot reach the server from outside:**
Make sure port 80 (and 443 if using HTTPS) is open in your server's firewall.

```bash
# Ubuntu/Debian
sudo ufw allow 80
sudo ufw allow 443
```

**MySQL connection refused from Micro Server:**
Verify that the database credentials in `aware-config.json` match `MYSQL_ROOT_PASSWORD` in `.env`. Note that MySQL does not allow the root user for remote connections by default — create a dedicated user in your `db/` init scripts.

**Configurator shows a blank page:**
The React frontend has the server address baked in at build time. If you change the domain or protocol, rebuild the Configurator:

```bash
docker compose build configurator
docker compose up -d configurator
```

## Project Structure

```
aware-dashboard/
├── .env                          # Environment variables (not committed to git)
├── .env.example                  # Template for .env
├── docker-compose.yml
├── nginx/
│   ├── http.conf                 # Nginx config for HTTP mode
│   └── https.conf                # Nginx config for HTTPS mode
├── db/
│   └── *.sql                     # MySQL initialization scripts
├── AWARE-Configurator/
│   ├── Dockerfile
│   ├── .dockerignore
│   └── ...                       # Django + React source code
├── aware-micro-server/
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── aware-config.json         # Micro server configuration
│   ├── cache/                    # Sensor icon cache
│   └── ...                       # Kotlin/Vert.x source code
└── certs/                        # SSL certificates (only for HTTPS)
    ├── fullchain.pem
    └── privkey.pem
```

## License

See [LICENSE](LICENSE) for details.
