<h1 align="center">Marzbun</h1>

<p align="center">
  A production-ready VPN management panel powered by <a href="https://github.com/XTLS/Xray-core">Xray-core</a> —
  fork of <a href="https://github.com/Gozargah/Marzban">Marzban</a> with an <strong>Admin Creation Quota System</strong>
  and a self-contained build-from-source installer.
</p>

<p align="center">
  <a href="https://github.com/Liwyd/marzbun/blob/master/LICENSE">
    <img src="https://img.shields.io/github/license/Liwyd/marzbun?style=flat-square" />
  </a>
  <img src="https://img.shields.io/badge/version-0.8.4-blue?style=flat-square" />
  <img src="https://img.shields.io/badge/python-3.12-blue?style=flat-square&logo=python" />
  <img src="https://img.shields.io/badge/xray--core-latest-green?style=flat-square" />
</p>

---

## Table of Contents

- [Features](#features)
- [Quick Install](#quick-install)
- [Install Options](#install-options)
- [Management Commands](#management-commands)
- [Configuration](#configuration)
- [Admin Quota System](#admin-quota-system)
- [Updating](#updating)
- [Uninstalling](#uninstalling)
- [CLI Reference](#cli-reference)
- [API Reference](#api-reference)
- [Architecture](#architecture)
- [License](#license)

---

## Features

All capabilities of upstream Marzban, **plus**:

| Feature | Description |
|---------|-------------|
| **Admin Creation Quota** | Sudo admins can cap how many total GB of user data each admin can provision |
| **Quota Audit Log** | Every allocation change is recorded in `admin_quota_logs` with full delta history |
| **Quota Rebuild CLI** | `marzbun cli admin quota-rebuild` repairs counters after direct DB edits |
| **Row-level Locking** | Quota checks are atomic — no over-allocation under concurrent requests |
| **Dashboard Quota Card** | Non-sudo admins see a live capacity progress bar with warning colours |
| **Self-contained Installer** | Builds the image directly from this repository — no Docker Hub account needed |

Core features inherited from Marzban:

- VMess · VLESS · Trojan · Shadowsocks (via Xray-core)
- Multi-node support with gRPC + mutual TLS
- Multiple subscription formats: v2ray, clash, sing-box, outline
- Per-user data limits, expiry, on-hold, next-plan auto-reset
- Telegram / Discord / Webhook notifications
- SQLite (default), MySQL, and MariaDB support
- Full REST API with OpenAPI docs

---

## Quick Install

> **Requirements:** Linux server, root access, internet connection.

```bash
bash <(curl -sSL https://raw.githubusercontent.com/Liwyd/marzbun/master/install.sh)
```

This single command will:

1. Install `git`, `curl`, `jq`, and Docker (if missing)
2. Clone this repository to `/opt/marzbun`
3. Build the Docker image locally from source
4. Generate `/opt/marzbun/.env` from the bundled template
5. Copy the default `xray_config.json` to `/var/lib/marzbun/`
6. Start the panel
7. Install the `marzbun` management command at `/usr/local/bin/marzbun`

After installation, open:

```
http://<your-server-ip>:8000/dashboard/
```

Create your first admin with:

```bash
marzbun cli admin create
```

---

## Install Options

### Default — SQLite database

```bash
bash <(curl -sSL https://raw.githubusercontent.com/Liwyd/marzbun/master/install.sh)
```

### MariaDB

```bash
bash <(curl -sSL https://raw.githubusercontent.com/Liwyd/marzbun/master/install.sh) --database mariadb
```

### MySQL

```bash
bash <(curl -sSL https://raw.githubusercontent.com/Liwyd/marzbun/master/install.sh) --database mysql
```

---

## Management Commands

After installation the `marzbun` command is available system-wide:

```
marzbun install         Install Marzbun (builds from source)
marzbun update          Pull latest source & rebuild image
marzbun uninstall       Remove Marzbun
marzbun up              Start services
marzbun down            Stop services
marzbun restart         Restart services
marzbun status          Show container status
marzbun logs            Follow live logs  (-n to dump & exit)
marzbun cli             Run marzban-cli inside the container
marzbun edit            Edit docker-compose.yml
marzbun edit-env        Edit .env
marzbun core-update     Install / switch Xray core version
marzbun backup          Create a manual backup archive
marzbun backup-service  Configure automatic Telegram backups
marzbun install-script  Re-install this management script
marzbun help            Show usage
```

---

## Configuration

All configuration lives in `/opt/marzbun/.env`. Edit it with:

```bash
marzbun edit-env
# then apply:
marzbun restart
```

### Key Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `UVICORN_HOST` | `0.0.0.0` | Bind address |
| `UVICORN_PORT` | `8000` | HTTP port |
| `SQLALCHEMY_DATABASE_URL` | SQLite path | Database connection string |
| `XRAY_JSON` | `/var/lib/marzban/xray_config.json` | Path to Xray inbound config |
| `XRAY_SUBSCRIPTION_PATH` | `sub` | URL prefix for subscription links |
| `SUDO_USERNAME` / `SUDO_PASSWORD` | — | Hard-coded sudo admin (prefer CLI) |
| `TELEGRAM_API_TOKEN` | — | Bot token for Telegram notifications |
| `WEBHOOK_ADDRESS` | — | Comma-separated webhook URLs |
| `NOTIFY_REACHED_USAGE_PERCENT` | `80,90` | Usage-warning thresholds (%) |
| `NOTIFY_DAYS_LEFT` | `3,7` | Days-left warning thresholds |

See `.env.example` in the repository for all available options.

---

## Admin Quota System

### Concept

Each admin account can optionally have a **creation quota** — a byte cap on the total `data_limit` they may allocate across all their users.

Example: admin `alice` has a 150 GB quota.

```
User A → 50 GB
User B → 30 GB
User C → 20 GB
─────────────
Allocated: 100 GB / 150 GB   Remaining: 50 GB
```

If alice tries to create a new 60 GB user, the request is rejected with an informative error.

### Accounting Rules

| Event | Quota effect |
|-------|-------------|
| Create user (50 GB) | +50 GB allocated |
| Modify user 50 → 80 GB | +30 GB allocated |
| Modify user 80 → 30 GB | −50 GB released |
| Delete user (50 GB) | −50 GB released |
| Transfer user **out** | −user.data\_limit on old admin |
| Transfer user **in** | +user.data\_limit on new admin |
| Admin quota set to unlimited | No enforcement |

> **Note:** Users with unlimited data (`data_limit = 0`) cannot be created by quota-limited admins.

### Setting Quota via API

```bash
# Set a 150 GB quota  (150 × 1024³ = 161061273600 bytes)
curl -X PUT "http://localhost:8000/api/admin/alice/quota?quota_bytes=161061273600" \
     -H "Authorization: Bearer <sudo-token>"

# Remove the quota (unlimited)
curl -X PUT "http://localhost:8000/api/admin/alice/quota" \
     -H "Authorization: Bearer <sudo-token>"

# View quota status
curl "http://localhost:8000/api/admin/alice/quota" \
     -H "Authorization: Bearer <token>"
```

### Setting Quota via CLI

```bash
# Create admin with a 150 GB quota
marzbun cli admin create --username alice --quota 150GB

# Update an existing admin's quota interactively
marzbun cli admin update --username alice
# Prompts show current quota; type a new value (e.g. "200GB") or "unlimited"

# Show all admins with Quota Limit / Allocated / Remaining columns
marzbun cli admin list
```

### Repairing Counters

If the counter ever gets out of sync (after a direct DB edit, data import, etc.):

```bash
marzbun cli admin quota-rebuild              # all quota-limited admins
marzbun cli admin quota-rebuild -u alice     # one admin only
```

### Dashboard

Non-sudo admins who have a quota limit see a **capacity card** on their dashboard:

- Progress bar (green → yellow → orange → red at 70 / 90 / 100 %)
- Bytes allocated vs. limit
- Bytes remaining

The user creation / edit form shows a real-time remaining-capacity hint under the data-limit field and prevents submission when the entered value would exceed the remaining quota.

---

## Updating

```bash
marzbun update
```

This pulls the latest commits from `https://github.com/Liwyd/marzbun`, rebuilds the Docker image, and restarts the service. Database migrations run automatically on the next startup.

---

## Uninstalling

```bash
marzbun uninstall
```

You will be asked whether to also delete the data directory (`/var/lib/marzbun`).

---

## CLI Reference

`marzbun cli <command>` runs commands inside the running container:

```bash
# Admin management
marzbun cli admin list
marzbun cli admin create --username alice --quota 150GB
marzbun cli admin update --username alice
marzbun cli admin delete --username alice
marzbun cli admin quota-rebuild

# User management
marzbun cli user list
marzbun cli user create --username bob
marzbun cli user delete --username bob
marzbun cli user reset  --username bob

# Subscription
marzbun cli subscription get --username bob
```

---

## API Reference

Enable the Swagger UI by adding `DOCS=True` to `.env` and restarting:

```
http://<server>:8000/docs
```

### Quota Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/admin/{username}/quota` | admin or sudo | Get quota status |
| `PUT` | `/api/admin/{username}/quota?quota_bytes=N` | sudo only | Set quota (omit param = unlimited) |
| `POST` | `/api/admin/{username}/quota/rebuild` | sudo only | Repair counter |

### Quota Response

```json
{
  "admin_username": "alice",
  "is_unlimited": false,
  "quota_limit": 161061273600,
  "allocated":   107374182400,
  "remaining":    53687091200,
  "usage_percent": 66.67
}
```

---

## Architecture

```
┌──────────────────────────────────────────┐
│  FastAPI  (single worker, host network)  │
│                                          │
│  Routers → CRUD → SQLAlchemy ORM         │
│  APScheduler background jobs             │
│  Xray-core subprocess (gRPC)             │
│  Remote nodes (gRPC over mTLS)           │
└──────────────────────────────────────────┘
         │                    │
   /var/lib/marzbun       Remote Nodes
   (persistent volume)    (marzban-node)
```

**Server paths:**

| Path | Contents |
|------|---------|
| `/opt/marzbun/` | Source code, docker-compose.yml, .env |
| `/var/lib/marzbun/` | SQLite DB, Xray config, TLS certs, custom Xray binary |
| `/usr/local/bin/marzbun` | Management script |

---

## License

[AGPL-3.0](LICENSE) — same as upstream Marzban.

---

<p align="center">Built on <a href="https://github.com/Gozargah/Marzban">Marzban</a> · Extended by <a href="https://github.com/Liwyd">Liwyd</a></p>
