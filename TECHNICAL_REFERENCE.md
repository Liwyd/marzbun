# Marzban — Technical Reference

> Version 0.8.4 — Comprehensive developer reference for adding features.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Technology Stack](#technology-stack)
3. [Project Structure](#project-structure)
4. [Database Schema](#database-schema)
5. [API Endpoints](#api-endpoints)
6. [Authentication & Authorization](#authentication--authorization)
7. [Configuration System](#configuration-system)
8. [Xray Integration](#xray-integration)
9. [Background Jobs](#background-jobs)
10. [Subscription System](#subscription-system)
11. [Notification System](#notification-system)
12. [Node Management](#node-management)
13. [User Lifecycle](#user-lifecycle)
14. [Proxy Protocols](#proxy-protocols)
15. [Frontend](#frontend)
16. [CLI](#cli)
17. [Deployment](#deployment)
18. [Adding Features — Patterns & Conventions](#adding-features--patterns--conventions)

---

## Architecture Overview

Marzban is a **multi-tenant VPN/proxy management panel** built on FastAPI with Xray as the core proxy engine. It manages users, credentials, traffic, and multiple distributed proxy servers (nodes) through a single API.

```
┌───────────────────────────────────────────────────────────┐
│  FastAPI Application (main.py + app/__init__.py)           │
│                                                            │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │   Routers    │  │  APScheduler │  │  Telegram Bot   │  │
│  │  (REST API)  │  │  (bg jobs)   │  │  Discord Hooks  │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬────────┘  │
│         │                 │                   │            │
│  ┌──────▼─────────────────▼───────────────────▼────────┐  │
│  │                   CRUD Layer (app/db/crud.py)        │  │
│  └──────────────────────────┬──────────────────────────┘  │
│                             │                              │
│  ┌──────────────────────────▼──────────────────────────┐  │
│  │         SQLAlchemy ORM (app/db/models.py)            │  │
│  │         SQLite / MySQL / PostgreSQL                  │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                            │
│  ┌─────────────────────────────────────────────────────┐  │
│  │          Xray Integration (app/xray/)                │  │
│  │   ┌─────────────┐   ┌────────────┐  ┌────────────┐  │  │
│  │   │ XRayCore    │   │ XRayNode   │  │ xray_api   │  │  │
│  │   │ (main proc) │   │ (gRPC)     │  │ (gRPC wrap)│  │  │
│  │   └─────────────┘   └────────────┘  └────────────┘  │  │
│  └─────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────┘
         │                        │
    Main Xray Core           Remote Nodes
    (local process)          (gRPC over TLS)
```

**Key design decisions:**
- Single-process server (APScheduler incompatible with multiprocessing)
- All proxy operations are async/threaded via `@threaded_function` decorator
- Users are identified in Xray by email = `{user_id}.{username}`
- Node communication uses gRPC with mutual TLS (cert stored in DB)

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Web Framework | FastAPI 0.115.2 + Uvicorn ASGI |
| Database ORM | SQLAlchemy 2.0.36 |
| Migrations | Alembic 1.14.0 |
| Scheduler | APScheduler 3.9.1 (BackgroundScheduler) |
| Auth | PyJWT 2.8.0 + OAuth2 + bcrypt |
| Validation | Pydantic v2 (2.10.4) |
| Proxy Engine | Xray (xray-core, runs as subprocess) |
| Node Protocol | gRPC (grpcio 1.67.1) |
| Telegram | pyTelegramBotAPI 4.9.0 |
| Config | python-decouple + python-dotenv |
| Frontend | Vite + React + TypeScript (Chakra UI) |
| Python | 3.12 |

---

## Project Structure

```
Marzban/
├── main.py                          # Entrypoint: uvicorn config, startup
├── config.py                        # All env-var config with defaults
├── requirements.txt
├── Dockerfile / docker-compose.yml
├── alembic.ini                      # DB migration config
├── xray_config.json                 # Xray inbound/outbound template
├── marzban-cli.py                   # CLI entrypoint
│
├── app/
│   ├── __init__.py                  # FastAPI app, scheduler, CORS, lifecycle
│   ├── dependencies.py              # FastAPI DI: get_db, get_current_admin, etc.
│   │
│   ├── db/
│   │   ├── base.py                  # SQLAlchemy engine + session factory (GetDB)
│   │   ├── models.py                # ALL ORM models (source of truth)
│   │   ├── crud.py                  # All DB operations (no raw SQL elsewhere)
│   │   └── migrations/              # Alembic version scripts
│   │
│   ├── models/                      # Pydantic request/response schemas
│   │   ├── user.py                  # UserCreate, UserModify, UserResponse, etc.
│   │   ├── admin.py                 # AdminCreate, AdminModify, Admin auth
│   │   ├── proxy.py                 # ProxyTypes, ProxySettings, ProxyHost
│   │   ├── node.py                  # NodeCreate, NodeModify, NodeStatus
│   │   ├── system.py                # SystemStats
│   │   ├── core.py                  # CoreStats
│   │   └── user_template.py         # UserTemplateCreate, UserTemplateModify
│   │
│   ├── routers/
│   │   ├── __init__.py              # api_router aggregator
│   │   ├── admin.py                 # /api/admin* endpoints
│   │   ├── user.py                  # /api/user* endpoints
│   │   ├── node.py                  # /api/node* endpoints
│   │   ├── subscription.py          # /{sub_path}/{token}/* endpoints
│   │   ├── core.py                  # /api/core* endpoints
│   │   ├── system.py                # /api/system, /api/inbounds, /api/hosts
│   │   ├── user_template.py         # /api/user_template* endpoints
│   │   └── home.py                  # GET / (HTML home page)
│   │
│   ├── xray/
│   │   ├── __init__.py              # Module-level singletons: api, config, nodes
│   │   ├── config.py                # XRayConfig: parses xray_config.json, generates configs
│   │   ├── core.py                  # XRayCore: manages xray subprocess
│   │   ├── node.py                  # XRayNode: gRPC node connection
│   │   └── operations.py            # add_user, remove_user, connect_node, etc.
│   │
│   ├── jobs/                        # APScheduler jobs (auto-loaded via import)
│   │   ├── 0_xray_core.py           # Core health check + node reconnect (10s)
│   │   ├── record_usages.py         # Traffic recording user+node (10s/30s)
│   │   ├── review_users.py          # Status transitions, next_plan (10s)
│   │   ├── reset_user_data_usage.py # Periodic data reset (hourly)
│   │   ├── remove_expired_users.py  # Auto-delete expired users
│   │   └── send_notifications.py    # Webhook delivery with retry (30s)
│   │
│   ├── subscription/                # Client config generators
│   │   ├── share.py                 # Share link builder (vmess://, vless://, etc.)
│   │   ├── v2ray.py                 # V2Ray base64 + JSON format
│   │   ├── clash.py                 # Clash/Clash-Meta YAML format
│   │   ├── singbox.py               # Sing-box JSON format
│   │   ├── outline.py               # Outline JSON format
│   │   └── funcs.py                 # Shared helpers (template rendering, etc.)
│   │
│   ├── utils/
│   │   ├── jwt.py                   # JWT issue/verify + subscription token encode/decode
│   │   ├── report.py                # Notification dispatch helpers
│   │   ├── notification.py          # Notification models + in-memory queue
│   │   ├── system.py                # OS-level utils (memory, CPU, disk)
│   │   ├── helpers.py               # calculate_expiration_days, calculate_usage_percent
│   │   ├── crypto.py                # Random string/UUID generation
│   │   ├── store.py                 # XRayNode storage helpers
│   │   ├── concurrency.py           # @threaded_function decorator
│   │   └── responses.py             # Standard response templates
│   │
│   ├── templates/                   # Jinja2 templates
│   │   ├── subscription/            # Subscription page HTML
│   │   ├── home/                    # Home page HTML
│   │   ├── clash/                   # Clash YAML templates
│   │   ├── singbox/                 # Sing-box JSON templates
│   │   ├── v2ray/                   # V2Ray JSON templates
│   │   └── mux/                     # Mux config templates
│   │
│   ├── telegram/                    # Telegram bot integration
│   ├── discord/                     # Discord webhook integration
│   └── dashboard/                   # Vite/React frontend (built → /dashboard/build/)
│
├── cli/                             # CLI commands (typer)
│   ├── admin.py
│   ├── user.py
│   ├── subscription.py
│   └── utils.py
│
└── xray_api/                        # gRPC wrapper for Xray API
    ├── base.py
    ├── proxyman.py                  # add/remove inbound users
    ├── stats.py                     # traffic statistics
    └── proto/                       # compiled protobuf files
```

---

## Database Schema

File: [app/db/models.py](app/db/models.py)

### `admins`

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| username | String(34) unique | Case-sensitive |
| hashed_password | String(128) | bcrypt |
| is_sudo | Boolean | Full system access |
| password_reset_at | DateTime nullable | Invalidates old tokens when set |
| telegram_id | BigInteger nullable | Links Telegram account |
| discord_webhook | String(1024) nullable | Per-admin Discord hook |
| users_usage | BigInteger | Aggregate traffic of owned users |
| created_at | DateTime | |

Relations: `users` → User[], `usage_logs` → AdminUsageLogs[]

### `admin_usage_logs`

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| admin_id | FK → admins.id | |
| used_traffic_at_reset | BigInteger | Traffic at time of reset |
| reset_at | DateTime | |

### `users`

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| username | String(34) NOCASE unique | 3–32 chars, `[a-zA-Z0-9_\-@.]` |
| status | Enum(UserStatus) | active/disabled/limited/expired/on_hold |
| used_traffic | BigInteger | Bytes consumed since last reset |
| data_limit | BigInteger nullable | 0/null = unlimited |
| data_limit_reset_strategy | Enum | no_reset/day/week/month/year |
| expire | Integer nullable | UTC timestamp; null = never |
| admin_id | FK → admins.id | Owner |
| sub_revoked_at | DateTime nullable | Marks subscription revocation |
| sub_updated_at | DateTime nullable | Last subscription fetch |
| sub_last_user_agent | String(512) nullable | Client UA on last sub fetch |
| created_at | DateTime | |
| note | String(500) nullable | |
| online_at | DateTime nullable | Last traffic activity |
| on_hold_expire_duration | BigInteger nullable | Seconds; null = N/A |
| on_hold_timeout | DateTime nullable | Auto-resume deadline |
| auto_delete_in_days | Integer nullable | +ve=delete after N days, -ve=never, null=global |
| edit_at | DateTime nullable | Last modification time |
| last_status_change | DateTime | For auto-delete grace period calc |
| next_plan_id | FK → next_plans.id | Nullable |

**Hybrid properties (computed):**
- `reseted_usage` — sum of all `UserUsageResetLogs.used_traffic_at_reset`
- `lifetime_used_traffic` — `reseted_usage + used_traffic`
- `last_traffic_reset_time` — last reset_at from logs, or created_at

**Instance properties (Python-only):**
- `excluded_inbounds` — `{ProxyType: [tag, ...]}`
- `inbounds` — `{ProxyType: [active_tag, ...]}` (config inbounds minus excluded)

Relations: `proxies`, `node_usages`, `notification_reminders`, `admin`, `next_plan`, `usage_logs`

### `next_plans`

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| user_id | FK → users.id | One per user (uselist=False) |
| data_limit | BigInteger | New data limit on activation |
| expire | Integer nullable | New expiry timestamp |
| add_remaining_traffic | Boolean | Add leftover traffic to new limit |
| fire_on_either | Boolean | Trigger on limited OR expired (vs both) |

### `user_templates`

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| name | String(64) unique | |
| data_limit | BigInteger | 0 = unlimited |
| expire_duration | BigInteger | Seconds (0 = no expiry) |
| username_prefix | String(20) nullable | |
| username_suffix | String(20) nullable | |

Relations: `inbounds` → ProxyInbound[] (many-to-many via `template_inbounds_association`)

### `user_usage_logs`

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| user_id | FK → users.id | |
| used_traffic_at_reset | BigInteger | Traffic captured at reset |
| reset_at | DateTime | |

### `proxies`

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| user_id | FK → users.id | |
| type | Enum(ProxyTypes) | vmess/vless/trojan/shadowsocks |
| settings | JSON | Protocol-specific credentials |

Relations: `excluded_inbounds` → ProxyInbound[] (many-to-many via `exclude_inbounds_association`)

### `inbounds`

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| tag | String(256) unique index | Xray inbound tag |

Relations: `hosts` → ProxyHost[]

### `hosts`

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| remark | String(256) | Display name (supports template vars) |
| address | String(256) | Server address (supports `{SERVER_IP}`) |
| port | Integer nullable | Override port; null = from inbound |
| path | String(256) nullable | WebSocket/gRPC path override |
| sni | String(1000) nullable | TLS SNI override |
| host | String(1000) nullable | HTTP Host header |
| security | Enum(ProxyHostSecurity) | inbound_default/none/tls/reality |
| alpn | Enum(ProxyHostALPN) | none/h3/h2/http1.1/h3,h2/h2,http1.1 |
| fingerprint | Enum(ProxyHostFingerprint) | none/chrome/firefox/safari/... |
| inbound_tag | FK → inbounds.tag | |
| allowinsecure | Boolean nullable | Skip cert validation |
| is_disabled | Boolean | Hide from subscriptions |
| mux_enable | Boolean | Enable multiplexing |
| fragment_setting | String(100) nullable | Fragment config JSON |
| noise_setting | String(2000) nullable | Noise obfuscation JSON |
| random_user_agent | Boolean | Randomize UA header |
| use_sni_as_host | Boolean | Copy SNI to Host header |

### `nodes`

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| name | String(256) NOCASE unique | |
| address | String(256) | IP or hostname |
| port | Integer | gRPC management port (default 62050) |
| api_port | Integer | Xray gRPC API port (default 62051) |
| xray_version | String(32) nullable | Reported after connect |
| status | Enum(NodeStatus) | connected/connecting/error/disabled |
| last_status_change | DateTime | |
| message | String(1024) nullable | Error message if any |
| created_at | DateTime | |
| uplink | BigInteger | Total uplink bytes |
| downlink | BigInteger | Total downlink bytes |
| usage_coefficient | Float | Traffic multiplier (default 1.0) |

Relations: `user_usages` → NodeUserUsage[], `usages` → NodeUsage[]

### `node_user_usages`

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| created_at | DateTime | Truncated to the hour |
| user_id | FK → users.id | |
| node_id | FK → nodes.id | null = main core |
| used_traffic | BigInteger | |

Unique constraint: `(created_at, user_id, node_id)`

### `node_usages`

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| created_at | DateTime | Truncated to the hour |
| node_id | FK → nodes.id | |
| uplink | BigInteger | |
| downlink | BigInteger | |

Unique constraint: `(created_at, node_id)`

### `notification_reminders`

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| user_id | FK → users.id | |
| type | Enum(ReminderType) | expiration_date/data_usage |
| threshold | Integer nullable | % or days value |
| expires_at | DateTime nullable | Reminder auto-expires |
| created_at | DateTime | |

### `system`

| Column | Type |
|--------|------|
| id | Integer PK |
| uplink | BigInteger |
| downlink | BigInteger |

### `jwt`

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| secret_key | String(64) | 32 random bytes hex-encoded |

### `tls`

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| key | String(4096) | PEM private key |
| certificate | String(2048) | PEM certificate |

---

## API Endpoints

All endpoints prefixed with `/api/` except subscription endpoints.

### Admin — `app/routers/admin.py`

```
POST   /api/admin/token                        Login → JWT token
POST   /api/admin                              Create admin (sudo)
GET    /api/admin                              Get current admin info
PUT    /api/admin/{username}                   Modify admin (sudo)
DELETE /api/admin/{username}                   Delete admin (sudo)
GET    /api/admins                             List all admins (sudo)
POST   /api/admin/{username}/users/disable     Disable admin's users
POST   /api/admin/{username}/users/activate    Activate admin's users
POST   /api/admin/usage/reset/{username}       Reset admin traffic counter
GET    /api/admin/usage/{username}             Get admin usage stats
```

### Users — `app/routers/user.py`

```
POST   /api/user                               Create user
GET    /api/user/{username}                    Get user
PUT    /api/user/{username}                    Update user
DELETE /api/user/{username}                    Delete user
POST   /api/user/{username}/reset              Reset user traffic
POST   /api/user/{username}/revoke_sub         Revoke subscription (rotates credentials)
POST   /api/user/{username}/active-next        Manually activate next_plan
GET    /api/users                              List users (search, filter, sort, paginate)
GET    /api/users/usage                        Aggregate traffic for admin's users
GET    /api/user/{username}/usage              Per-node usage for user
POST   /api/users/reset                        Reset all users' traffic (sudo)
GET    /api/users/expired                      List expired users
DELETE /api/users/expired                      Bulk-delete expired users
PUT    /api/user/{username}/set-owner          Transfer user to another admin (sudo)
```

### Nodes — `app/routers/node.py`

```
GET    /api/node/settings                      Get TLS cert (for node setup)
POST   /api/node                               Add node
GET    /api/node/{node_id}                     Get node
PUT    /api/node/{node_id}                     Modify node
DELETE /api/node/{node_id}                     Delete node
POST   /api/node/{node_id}/reconnect           Force reconnect
GET    /api/nodes                              List all nodes
GET    /api/nodes/usage                        Node bandwidth usage (sudo)
WS     /api/node/{node_id}/logs                Live node logs (sudo)
```

### Subscriptions — `app/routers/subscription.py`

```
GET    /{SUB_PATH}/{token}/                    Auto-detect client, return subscription
GET    /{SUB_PATH}/{token}/info                Subscription metadata (JSON)
GET    /{SUB_PATH}/{token}/usage               Remaining data/time
GET    /{SUB_PATH}/{token}/{client_type}       Force specific format:
                                                 sing-box | clash-meta | clash |
                                                 outline | v2ray | v2ray-json
```

Default `SUB_PATH` = `sub` (configurable via `XRAY_SUBSCRIPTION_PATH`).

**Auto-detection logic** (subscription.py:81–139):
- User-Agent strings matched: v2rayNG, v2rayN, clash-meta, clash, sing-box, outline, Happ, Streisand
- Version-specific: v2rayN ≥ 6.40 uses v2ray-json format
- Fallback: base64 v2ray links

### Core — `app/routers/core.py`

```
GET    /api/core                               Core stats (version, started, etc.)
POST   /api/core/restart                       Restart Xray core (sudo)
GET    /api/core/config                        Get current Xray JSON config (sudo)
PUT    /api/core/config                        Replace Xray JSON config (sudo)
WS     /api/core/logs                          Stream Xray core logs (sudo)
```

### System — `app/routers/system.py`

```
GET    /api/system                             System stats (mem, cpu, disk, user counts)
GET    /api/inbounds                           All inbounds grouped by protocol
GET    /api/hosts                              All hosts (sudo)
PUT    /api/hosts                              Replace all hosts (sudo)
```

### User Templates — `app/routers/user_template.py`

```
POST   /api/user_template                      Create template (sudo)
GET    /api/user_template/{id}                 Get template
PUT    /api/user_template/{id}                 Modify template (sudo)
DELETE /api/user_template/{id}                 Delete template (sudo)
GET    /api/user_template                      List templates
```

---

## Authentication & Authorization

### Admin JWT

File: [app/utils/jwt.py](app/utils/jwt.py), [app/models/admin.py](app/models/admin.py)

1. Client POSTs `username`+`password` to `/api/admin/token` (OAuth2 form)
2. Server checks:
   - **SUDOERS dict** (from env `SUDO_USERNAME`/`SUDO_PASSWORD`) first
   - **Database admins** (bcrypt hash compare)
3. Issues HS256 JWT with claims: `sub` (username), `access` (`sudo` | `admin`)
4. JWT expiry: `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` (default 1440 = 24h)
5. `password_reset_at` in Admin row invalidates tokens issued before that time

**Dependency injection** (dependencies.py):
```python
# Any authenticated admin
Admin = Depends(get_current_admin)

# Sudo-only
Admin = Depends(get_sudo_admin)

# Validated user (admin must own, unless sudo)
User = Depends(get_validated_user)
```

### Subscription Token

File: [app/utils/jwt.py](app/utils/jwt.py):47–88

Custom format (not JWT):
```
base64("{user_id},{username},{timestamp}") + "." + base64(HMAC-SHA256[:10])
```

- Signed with JWT secret from DB
- Revocable: if `token_timestamp < user.sub_revoked_at`, subscription returns 403
- Tokens are stable until explicitly revoked

---

## Configuration System

File: [config.py](config.py) — uses `python-decouple` (reads `.env` file or environment).

### Database
```
SQLALCHEMY_DATABASE_URL        sqlite:///db.sqlite3
SQLALCHEMY_POOL_SIZE           10
SQLIALCHEMY_MAX_OVERFLOW       30
```

### Server
```
UVICORN_HOST                   0.0.0.0
UVICORN_PORT                   8000
UVICORN_UDS                    (Unix socket, alternative to host:port)
UVICORN_SSL_CERTFILE           (path to cert)
UVICORN_SSL_KEYFILE            (path to key)
UVICORN_SSL_CA_TYPE            public
DASHBOARD_PATH                 /dashboard/
DEBUG                          False
DOCS                           False   (enables /docs and /redoc)
ALLOWED_ORIGINS                *
```

### Xray
```
XRAY_JSON                      ./xray_config.json
XRAY_EXECUTABLE_PATH           /usr/local/bin/xray
XRAY_ASSETS_PATH               /usr/local/share/xray
XRAY_EXCLUDE_INBOUND_TAGS      (space-separated tags to exclude)
XRAY_SUBSCRIPTION_PATH         sub
XRAY_SUBSCRIPTION_URL_PREFIX   (prepended to subscription URLs)
XRAY_FALLBACKS_INBOUND_TAG     (fallback inbound for Xray config)
```

### Authentication
```
SUDO_USERNAME                  (hard-coded sudo admin)
SUDO_PASSWORD                  (hard-coded sudo password)
JWT_ACCESS_TOKEN_EXPIRE_MINUTES 1440
```

### Subscription Client Flags
```
USE_CUSTOM_JSON_DEFAULT        False
USE_CUSTOM_JSON_FOR_V2RAYN     False
USE_CUSTOM_JSON_FOR_V2RAYNG    False
USE_CUSTOM_JSON_FOR_STREISAND  False
USE_CUSTOM_JSON_FOR_HAPP       False
```

### Templates
```
CUSTOM_TEMPLATES_DIRECTORY     (override built-in templates)
SUBSCRIPTION_PAGE_TEMPLATE     subscription/index.html
HOME_PAGE_TEMPLATE             home/index.html
CLASH_SUBSCRIPTION_TEMPLATE    clash/default.yml
SINGBOX_SUBSCRIPTION_TEMPLATE  singbox/default.json
V2RAY_SUBSCRIPTION_TEMPLATE    v2ray/default.json
MUX_TEMPLATE                   mux/default.json
```

### Notifications
```
WEBHOOK_ADDRESS                (comma-separated URLs)
WEBHOOK_SECRET                 (HMAC-SHA256 signing key)
TELEGRAM_API_TOKEN
TELEGRAM_ADMIN_ID              (comma-separated int IDs)
TELEGRAM_PROXY_URL
TELEGRAM_LOGGER_CHANNEL_ID
DISCORD_WEBHOOK_URL

NOTIFY_STATUS_CHANGE           True
NOTIFY_USER_CREATED            True
NOTIFY_USER_UPDATED            True
NOTIFY_USER_DELETED            True
NOTIFY_USER_DATA_USED_RESET    True
NOTIFY_USER_SUB_REVOKED        True
NOTIFY_IF_DATA_USAGE_PERCENT_REACHED  True
NOTIFY_IF_DAYS_LEFT_REACHED    True
NOTIFY_LOGIN                   True
LOGIN_NOTIFY_WHITE_LIST        (comma-sep IPs exempt from login notifications)

RECURRENT_NOTIFICATIONS_TIMEOUT       180   (retry interval seconds)
NUMBER_OF_RECURRENT_NOTIFICATIONS     3
NOTIFY_REACHED_USAGE_PERCENT   80    (comma-sep %, e.g. "70,90")
NOTIFY_DAYS_LEFT               3     (comma-sep days, e.g. "3,7")
```

### User Auto-Delete
```
USERS_AUTODELETE_DAYS          -1    (-1 = disabled globally)
USER_AUTODELETE_INCLUDE_LIMITED_ACCOUNTS  False
```

### Job Intervals (seconds)
```
JOB_CORE_HEALTH_CHECK_INTERVAL       10
JOB_RECORD_NODE_USAGES_INTERVAL      30
JOB_RECORD_USER_USAGES_INTERVAL      10
JOB_REVIEW_USERS_INTERVAL            10
JOB_SEND_NOTIFICATIONS_INTERVAL      30
```

### Subscription Headers
```
SUB_UPDATE_INTERVAL            12    (hours)
SUB_SUPPORT_URL                https://t.me/
SUB_PROFILE_TITLE              Subscription
```

### Status Text Overrides
```
ACTIVE_STATUS_TEXT             Active
EXPIRED_STATUS_TEXT            Expired
LIMITED_STATUS_TEXT            Limited
DISABLED_STATUS_TEXT           Disabled
ONHOLD_STATUS_TEXT             On-Hold
```

---

## Xray Integration

Files: [app/xray/](app/xray/)

### Module-level singletons — `app/xray/__init__.py`

```python
xray.api      # XRayAPI (gRPC client for main core)
xray.config   # XRayConfig (parsed xray_config.json + DB hosts)
xray.core     # XRayCore (subprocess manager)
xray.nodes    # Dict[int, XRayNode] (connected remote nodes)
```

### XRayCore — `app/xray/core.py`

- Runs `xray` binary as a subprocess
- Reads `XRAY_JSON`, injects inbound users before starting
- `on_start(callback)` / `on_stop(callback)` hooks for lifecycle
- Restartable: stops process, regenerates config with current DB users, starts again

### XRayConfig — `app/xray/config.py`

- Parses `xray_config.json`
- Exposes: `inbounds_by_tag`, `inbounds_by_protocol`
- `include_db_users()` → generates full config with all active users added to inbounds
- Respects `XRAY_EXCLUDE_INBOUND_TAGS` and `XRAY_FALLBACKS_INBOUND_TAG`

### XRayNode — `app/xray/node.py`

- gRPC connection to remote Marzban-node service
- Methods: `start(config)`, `restart(config)`, `disconnect()`, `get_version()`
- `node.api` → XRayAPI instance for that node
- `node.connected` / `node.started` → connection state

### operations.py — `app/xray/operations.py`

Core functions (all thread-safe via `@threaded_function`):

```python
add_user(dbuser)       # Add to main core + all connected nodes
remove_user(dbuser)    # Remove from main core + all connected nodes
update_user(dbuser)    # Alter credentials in main core + all nodes
                       # Also removes from disabled inbounds

add_node(dbnode)       # Create XRayNode instance
remove_node(node_id)   # Disconnect + delete from xray.nodes
connect_node(node_id)  # Deploy full config to node (threaded)
restart_node(node_id)  # Restart xray on node with updated config (threaded)
```

**User email format:** `{user.id}.{user.username}` — this is how Xray identifies users across inbounds.

**XTLS flow caveat:** `flow` is set to `NONE` unless:
- Network is `tcp` or `kcp` AND
- TLS is `tls` or `reality` AND
- Header type is not `http`

---

## Background Jobs

All jobs are registered with APScheduler in their respective files via:
```python
scheduler.add_job(fn, 'interval', seconds=N, coalesce=True, max_instances=1)
```

The scheduler starts at app startup. Each job file is auto-imported by `app/jobs/__init__.py`.

### Core Health Check — `app/jobs/0_xray_core.py` (10s)

1. Checks if main Xray core is running → restarts if not
2. Iterates `xray.nodes` → calls `connect_node()` for disconnected/error nodes

### Record User Usages — `app/jobs/record_usages.py` (10s)

1. Queries gRPC stats for all users from main core and each node
2. Applies `node.usage_coefficient` to reported traffic
3. Writes/upserts `NodeUserUsage` records (hourly buckets)
4. Accumulates into `User.used_traffic`
5. Also updates `Admin.users_usage` for each user's admin
6. MySQL deadlock retry logic included

### Record Node Usages — same file (30s)

1. Queries gRPC for node-level uplink/downlink
2. Writes/upserts `NodeUsage` records (hourly buckets)
3. Updates `Node.uplink` / `Node.downlink` totals

### Review Users — `app/jobs/review_users.py` (10s)

Iterates all `active` users:
- `limited = used_traffic >= data_limit`
- `expired = expire <= now_ts`
- If `(limited OR expired)` AND `next_plan` exists:
  - `fire_on_either=True` → activate next_plan immediately
  - `fire_on_either=False` → only activate when BOTH conditions met
- Otherwise: set status to `limited` or `expired`, remove from Xray, send notification

Iterates all `on_hold` users:
- If `online_at >= edit_at` (user connected after last edit) → transition to `active`
- If `on_hold_timeout <= now` → transition to `active`
- On activation: `start_user_expire()` sets `expire = now + on_hold_expire_duration`

Also manages notification reminders for usage % and days-left thresholds.

### Reset User Data Usage — `app/jobs/reset_user_data_usage.py` (hourly)

For each user with a reset strategy:
- `day`: Reset every 24h from `last_traffic_reset_time`
- `week`: Reset every 7 days
- `month`: Reset every 30 days
- `year`: Reset every 365 days
- `no_reset`: Never

On reset: logs traffic to `UserUsageResetLogs`, clears `used_traffic`, re-activates if needed.

### Remove Expired Users — `app/jobs/remove_expired_users.py`

Calls `crud.autodelete_expired_users()` which:
- Finds users with `status IN (expired[, limited])` AND `auto_delete_in_days >= 0`
- Checks `last_status_change + auto_delete_in_days <= now`
- Deletes matching users from DB (cascade removes proxies, usages)

### Send Notifications — `app/jobs/send_notifications.py` (30s)

Drains `notification.queue` (a `collections.deque`):
- POSTs JSON to each `WEBHOOK_ADDRESS` with optional HMAC-SHA256 signature header
- `X-Webhook-Secret` header = HMAC of payload
- Retry logic: up to `NUMBER_OF_RECURRENT_NOTIFICATIONS` tries, `RECURRENT_NOTIFICATIONS_TIMEOUT` seconds between retries
- Failed notifications are re-queued with updated `send_at`

---

## Subscription System

Files: [app/subscription/](app/subscription/), [app/routers/subscription.py](app/routers/subscription.py)

### Subscription URL

```
GET /{XRAY_SUBSCRIPTION_PATH}/{token}/
```

The token encodes user identity + timestamp, signed with JWT secret. The system tracks `sub_updated_at` and `sub_last_user_agent` on each fetch.

### Subscription Response Headers

```
Content-Disposition: attachment; filename="<username>"
profile-update-interval: <SUB_UPDATE_INTERVAL>
support-url: <SUB_SUPPORT_URL>
subscription-userinfo: upload=0; download=<used>; total=<limit>; expire=<ts>
profile-title: base64(<SUB_PROFILE_TITLE>)
```

### Client Format Selection

Priority:
1. Explicit `/{client_type}` URL segment
2. User-Agent pattern matching (subscription.py:81–139)
3. Fallback: v2ray base64

### Format Details

**V2Ray base64** — `app/subscription/v2ray.py`
- Returns newline-separated proxy URIs, base64-encoded
- URI schemes: `vmess://`, `vless://`, `trojan://`, `ss://`

**V2Ray JSON** — same file
- Returns JSON config format (for v2rayN ≥ 6.40, v2rayNG, etc.)
- Uses `V2RAY_SUBSCRIPTION_TEMPLATE` Jinja2 template

**Clash/Clash-Meta** — `app/subscription/clash.py`
- Returns YAML config
- Uses `CLASH_SUBSCRIPTION_TEMPLATE`

**Sing-box** — `app/subscription/singbox.py`
- Returns JSON config
- Uses `SINGBOX_SUBSCRIPTION_TEMPLATE`

**Outline** — `app/subscription/outline.py`
- Returns JSON array of `ss://` links

### Share Link Builder — `app/subscription/share.py`

Generates individual proxy URIs given a user + inbound config.

Variables available in host `remark`/`address` templates:
```
{USERNAME}    user.username
{DATA_USAGE}  formatted bytes
{DATA_LIMIT}  formatted bytes
{IP}          resolved server IP
{SERVER_IP}   server IP
{PROTOCOL}    protocol name
{TRANSPORT}   network type
```

---

## Notification System

Files: [app/utils/notification.py](app/utils/notification.py), [app/utils/report.py](app/utils/report.py)

### Queue

`notification.queue` is a `collections.deque`. `notify(msg)` appends to it.

### Notification Types

```python
class Notification.Type(str, Enum):
    user_created
    user_updated
    user_deleted
    user_limited
    user_expired
    user_enabled
    user_disabled
    data_usage_reset
    data_reset_by_next
    subscription_revoked
    reached_usage_percent
    reached_days_left
```

### Notification Models (Pydantic)

All extend `Notification`:
- `UserCreated(user, by)` — `by` = Admin
- `UserUpdated(user, by)`
- `UserDeleted(by)`
- `UserLimited(user)`
- `UserExpired(user)`
- `UserEnabled(user, by=None)`
- `UserDisabled(user, by, reason=None)`
- `UserDataUsageReset(user, by)`
- `UserDataResetByNext(user)`
- `UserSubscriptionRevoked(user, by)`
- `ReachedUsagePercent(user, used_percent)`
- `ReachedDaysLeft(user, days_left)`

### Report Helpers — `app/utils/report.py`

Functions like `report.status_change()`, `report.user_created()`, etc. dispatch notifications to:
1. Webhook queue (via `notify()`)
2. Telegram bot (if configured)
3. Discord webhook (if configured)

---

## Node Management

Files: [app/models/node.py](app/models/node.py), [app/xray/node.py](app/xray/node.py), [app/routers/node.py](app/routers/node.py)

### Node Status Flow

```
(created) → connecting → connected
                      ↘ error → (reconnect attempt every health-check cycle)
disabled (manual)
```

### Node Setup (for operators)

1. Install `marzban-node` service on remote server
2. Add node via `POST /api/node` with `address`, `port`, `api_port`
3. Get TLS cert via `GET /api/node/settings`
4. Configure cert on marzban-node, restart it
5. Panel auto-connects via health-check job

### gRPC Communication

- Marzban → node: management gRPC on `port` (default 62050)
- Marzban → node Xray: Xray gRPC API on `api_port` (default 62051)
- Authenticated with mutual TLS (cert from `tls` DB table)

### `usage_coefficient`

Traffic reported by a node is multiplied by this value before being added to `user.used_traffic`. Allows pricing different bandwidth differently (e.g., premium bandwidth = 2×).

---

## User Lifecycle

### Status Transitions

```
on_hold ──(online_at updated)──────────────────→ active
on_hold ──(on_hold_timeout reached)────────────→ active
active  ──(data_limit exceeded)────────────────→ limited
active  ──(expire reached)─────────────────────→ expired
active  ──(manual disable)─────────────────────→ disabled
limited ──(manual reset or new data_limit set)─→ active
expired ──(new expire set in future)───────────→ active
disabled──(manual activate)────────────────────→ active
* ──(next_plan fires)──────────────────────────→ active (with new plan)
```

### next_plan Activation

When `review_users` detects `limited OR expired`:
1. `fire_on_either=True` → fire immediately on first condition
2. `fire_on_either=False` → fire only when BOTH `limited AND expired`

On firing:
- Logs current `used_traffic` to `UserUsageResetLogs`
- Sets `data_limit = next_plan.data_limit + (remaining if add_remaining_traffic)`
- Sets `expire = next_plan.expire`
- Resets `used_traffic = 0`
- Sets `status = active`
- Deletes the `next_plan` record

### Subscription Revocation

`POST /api/user/{username}/revoke_sub`:
1. Sets `sub_revoked_at = now`
2. Calls `settings.revoke()` on each proxy type:
   - VMess/VLESS: generates new UUID
   - Trojan/Shadowsocks: generates new password
3. Updates user in Xray (removes old credentials, adds new)
4. Future subscription fetches with old token return 403 (token timestamp < sub_revoked_at)

---

## Proxy Protocols

File: [app/models/proxy.py](app/models/proxy.py)

### ProxyTypes

```python
class ProxyTypes(str, Enum):
    VMess = "vmess"
    VLESS = "vless"
    Trojan = "trojan"
    Shadowsocks = "shadowsocks"
```

Each type has an `account_model` (from `xray_api`) and a `settings_model` (Pydantic).

### Settings per Protocol

**VMess:**
```json
{"id": "<UUID>"}
```

**VLESS:**
```json
{"id": "<UUID>", "flow": "xtls-rprx-vision" | ""}
```

**Trojan:**
```json
{"password": "<random>", "flow": "xtls-rprx-vision" | ""}
```

**Shadowsocks:**
```json
{"password": "<random>", "method": "chacha20-ietf-poly1305"}
```

Methods: `chacha20-ietf-poly1305`, `aes-256-gcm`, `aes-128-gcm`

### ProxyHostSecurity
`inbound_default` | `none` | `tls` | `reality`

### ProxyHostALPN
`""` (none) | `h3` | `h2` | `http/1.1` | `h3,h2` | `h2,http/1.1` | `h3,h2,http/1.1`

### ProxyHostFingerprint
`""` (none) | `chrome` | `firefox` | `safari` | `ios` | `android` | `edge` | `qq` | `random` | `randomized`

---

## Frontend

Directory: [app/dashboard/](app/dashboard/)

- **Build tool:** Vite
- **Framework:** React + TypeScript
- **UI library:** Chakra UI
- **API base:** `VITE_BASE_API` env var (default `/api/`)
- **Built output:** `app/dashboard/build/` → served by FastAPI at `DASHBOARD_PATH`
- **Dev mode:** `DEBUG=True` starts Vite dev server automatically, proxies API to `http://127.0.0.1:{UVICORN_PORT}/api/`

Static assets served at `/statics/`.

---

## CLI

File: [marzban-cli.py](marzban-cli.py), [cli/](cli/)

Built with Typer. Commands:

```
marzban-cli admin  create/list/update/delete/import-from-env
marzban-cli user   list/get/create/delete/reset/set-owner
marzban-cli subscription get
```

---

## Deployment

### Docker

```yaml
# docker-compose.yml
services:
  marzban:
    image: gozargah/marzban:latest
    network_mode: host        # shares host network
    volumes:
      - /var/lib/marzban:/var/lib/marzban
    env_file: .env
```

**Dockerfile:**
1. Stage 1: installs deps, downloads Xray binary
2. Stage 2: clean runtime, runs `alembic upgrade head` then `python main.py`

### main.py startup sequence

1. Alembic `upgrade head` (migrations)
2. `uvicorn.run()` with config from env
3. FastAPI startup event:
   - APScheduler starts
   - Dashboard build (if DEBUG: Vite dev; else: serve static)
4. Jobs auto-register via import
5. Xray core starts (via `0_xray_core.py` job on first tick)

---

## Adding Features — Patterns & Conventions

### Adding a new API endpoint

1. Add route to appropriate router in `app/routers/`
2. Add Pydantic schema to `app/models/` if needed
3. Add CRUD function to `app/db/crud.py`
4. Add DB migration if schema changed: `alembic revision --autogenerate -m "description"`
5. If the endpoint changes user proxy state → call `xray.operations.update_user()` or `add_user()`/`remove_user()`
6. If endpoint should trigger notifications → call `report.*()` or `notification.notify()`

### Adding a new DB column

1. Add column to `app/db/models.py`
2. Add field to relevant Pydantic model in `app/models/`
3. Update CRUD functions in `app/db/crud.py`
4. Run `alembic revision --autogenerate -m "add <column> to <table>"` to generate migration
5. Verify migration in `app/db/migrations/versions/`

### Adding a new background job

1. Create `app/jobs/my_job.py`
2. Import scheduler: `from app import scheduler`
3. Define function and register: `scheduler.add_job(fn, 'interval', seconds=N, coalesce=True, max_instances=1)`
4. The job auto-runs because `app/jobs/__init__.py` imports all files in the jobs directory

### Adding a new notification type

1. Add enum value to `Notification.Type` in `app/utils/notification.py`
2. Add model class extending `UserNotification`
3. Add helper in `app/utils/report.py`
4. Call from wherever the event occurs
5. Handler in `app/jobs/send_notifications.py` picks it up automatically

### Adding a new proxy client format

1. Create `app/subscription/my_format.py`
2. Implement `generate(user, hosts, ...)` → str
3. Add detection logic in `app/routers/subscription.py` User-Agent matching
4. Add `/{client_type}` route handler

### Database session pattern

```python
# In routes (dependency injection):
def my_route(db: Session = Depends(get_db)):
    result = crud.some_function(db, ...)

# In jobs/background tasks:
from app.db import GetDB
with GetDB() as db:
    result = crud.some_function(db, ...)
```

### Threaded operations pattern

```python
from app.utils.concurrency import threaded_function

@threaded_function
def my_async_operation(arg1, arg2):
    # runs in a thread pool
    pass
```

### Testing a change

No automated test suite in this repo. To test:
1. Run with `DEBUG=True` for auto-reload + Vite dev server
2. Use `/docs` endpoint (requires `DOCS=True`) for Swagger UI
3. Check logs via `WS /api/core/logs` or stdout

---

*End of Technical Reference*
