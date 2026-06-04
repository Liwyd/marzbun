# Local Development Guide

Complete setup instructions for running Marzban on a developer machine.

---

## Prerequisites

| Tool | Required | Notes |
|------|----------|-------|
| Python 3.11+ | Yes | `python3 --version` |
| pip | Yes | bundled with Python |
| Node.js 18+ | Yes | `node --version` |
| npm 9+ | Yes | `npm --version` |
| Xray binary | No | Only needed for full proxy functionality — see [Xray section](#xray-in-development) |
| Docker + Compose | No | Alternative to native setup — see [Docker section](#docker-development-environment) |

---

## Quick Start (5 steps)

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Install frontend dependencies
cd app/dashboard && npm install && cd ../..

# 3. Copy development env file
cp .env.development .env

# 4. Run DB migrations + seed test data
alembic upgrade head
python scripts/seed.py

# 5. Start the backend (also auto-starts the Vite dev server)
python main.py
```

Open http://127.0.0.1:8000/dashboard/ — log in with `admin` / `admin123`.

---

## Environment Variables

The `.env.development` file contains all variables with safe local defaults.
Copy it to `.env` before starting:

```bash
cp .env.development .env
```

Key variables and their dev values:

| Variable | Dev default | Purpose |
|----------|-------------|---------|
| `DEBUG` | `True` | Enables auto-reload, starts Vite dev server |
| `DOCS` | `True` | Enables Swagger UI at `/docs` |
| `SQLALCHEMY_DATABASE_URL` | `sqlite:///dev.sqlite3` | Zero-setup local DB |
| `XRAY_ENABLED` | `False` | Skip Xray startup when binary is not installed |
| `SUDO_USERNAME` | `admin` | Used by `import-from-env` CLI command |
| `SUDO_PASSWORD` | `admin123` | Used by `import-from-env` CLI command |
| `ALLOWED_ORIGINS` | `*` | No CORS restrictions in dev |

Full reference: [`.env.development`](.env.development) and [`config.py`](config.py).

---

## Database

### SQLite (default — zero setup)

The dev DB file is `dev.sqlite3` in the project root.

```bash
# Apply all migrations (run after every `git pull` that adds new migrations)
alembic upgrade head

# Check current migration state
alembic current

# Reset: delete DB and re-migrate
rm -f dev.sqlite3 && alembic upgrade head && python scripts/seed.py
```

### PostgreSQL (optional)

1. Start a local Postgres instance (Docker is the easiest):
   ```bash
   docker run -d --name marzban-pg \
     -e POSTGRES_USER=marzban \
     -e POSTGRES_PASSWORD=marzban \
     -e POSTGRES_DB=marzban_dev \
     -p 5432:5432 postgres:16
   ```

2. Update `.env`:
   ```
   SQLALCHEMY_DATABASE_URL=postgresql://marzban:marzban@localhost:5432/marzban_dev
   ```

3. Run migrations:
   ```bash
   alembic upgrade head
   ```

---

## Seed Data

The seed script creates dev accounts and sample users. It is idempotent — safe to re-run.

```bash
python scripts/seed.py
```

### Created accounts

| Type | Username | Password |
|------|----------|----------|
| Sudo admin | `admin` | `admin123` |
| Regular admin | `testadmin` | `admin123` |

### Created sample users

| Username | Status | Data Limit | Expiry |
|----------|--------|------------|--------|
| `user_limited` | active | 10 GB | 30 days |
| `user_unlimited` | active | unlimited | never |
| `user_expired` | expired | 5 GB | yesterday |
| `user_disabled` | disabled | unlimited | never |
| `user_onhold` | on_hold | 3 GB | — |

---

## Starting the Backend

```bash
python main.py
```

With `DEBUG=True` the server starts with:
- Host `0.0.0.0`, port `8000`
- Auto-reload on code changes (`uvicorn --reload`)
- Full Python tracebacks in responses
- Swagger UI at http://127.0.0.1:8000/docs
- Vite dev server auto-started at http://127.0.0.1:3000

To run with verbose SQL logging:
```bash
SQLALCHEMY_ECHO=True python main.py
```

---

## Starting the Frontend

### Automatic (recommended)

When `DEBUG=True`, the backend automatically starts the Vite dev server on port 3000 as a subprocess. Just run `python main.py` and navigate to http://127.0.0.1:8000/dashboard/.

The dashboard URL (`/dashboard/`) proxies the login page; direct API calls go to port 8000.

### Manual (standalone frontend)

Useful for frontend-only iteration without restarting the backend.

```bash
cd app/dashboard
npm run dev
```

This starts Vite on http://localhost:3000. The `vite.config.ts` proxy forwards `/api/` and `/sub/` requests to the backend at port 8000.

For hot-module-replacement to reach the backend, the backend must already be running.

```bash
# Terminal 1 — backend (no auto Vite start)
DEBUG=False DOCS=True python main.py

# Terminal 2 — frontend standalone
cd app/dashboard
VITE_BASE_API=/api/ npm run dev
```

---

## Xray in Development

Xray is the proxy core. For developing the admin UI, API, and database layer you **do not need Xray installed**.

### Option A — Disable Xray (default for local dev)

`.env.development` sets `XRAY_ENABLED=False`. The app starts fully: DB, API, dashboard, scheduler all work. Proxy configs are stored in the DB but not activated. User CRUD, statistics, and all management screens work normally.

### Option B — Install Xray locally

```bash
# Linux (x86_64)
sudo bash -c "$(curl -L https://github.com/Gozargah/Marzban-scripts/raw/master/install_latest_xray.sh)"
```

Then update `.env`:
```
XRAY_ENABLED=True
XRAY_EXECUTABLE_PATH=/usr/local/bin/xray
XRAY_ASSETS_PATH=/usr/local/share/xray
```

Verify:
```bash
xray version
```

### Option C — Use Docker (Xray included in the image)

See [Docker Development Environment](#docker-development-environment). The Docker image installs Xray at build time so it is available inside the container.

---

## API Testing with Swagger

Swagger UI is available at http://127.0.0.1:8000/docs when `DOCS=True`.

### Authentication flow

1. Open http://127.0.0.1:8000/docs
2. Click **Authorize** (top right)
3. Use the `/api/admin/token` endpoint to get a bearer token:
   - `username`: `admin`
   - `password`: `admin123`
4. Copy the `access_token` value
5. Paste it into the Authorize dialog: `Bearer <token>`

### Common API examples (curl)

```bash
BASE=http://127.0.0.1:8000/api

# Get token
TOKEN=$(curl -s -X POST "$BASE/admin/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin123" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# List users
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/users" | python3 -m json.tool

# Create a user
curl -s -X POST "$BASE/user" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"username":"newuser","proxies":{"shadowsocks":{}},"inbounds":{"shadowsocks":["Shadowsocks TCP"]},"data_limit":0,"expire":0,"status":"active"}' \
  | python3 -m json.tool

# Delete a user
curl -s -X DELETE -H "Authorization: Bearer $TOKEN" "$BASE/user/newuser"

# List admins (sudo only)
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/admins" | python3 -m json.tool
```

---

## CLI Commands

All CLI commands operate directly on the database using the same `.env` file.

```bash
# Create a sudo admin interactively
python marzban-cli.py admin create

# Import admin from SUDO_USERNAME / SUDO_PASSWORD env vars
python marzban-cli.py admin import-from-env --yes

# List admins
python marzban-cli.py admin list

# Update an admin
python marzban-cli.py admin update --username admin

# Delete an admin
python marzban-cli.py admin delete --username testadmin

# List users
python marzban-cli.py user list

# Reset user traffic
python marzban-cli.py user reset-usage --username user_limited

# Delete a user
python marzban-cli.py user delete --username user_disabled

# List subscriptions
python marzban-cli.py subscription list
```

---

## Debugging

### Backend — VSCode

1. Open the project in VSCode.
2. Install the **Python** extension (ms-python.python).
3. Select your virtualenv as the Python interpreter (`Ctrl+Shift+P` → "Python: Select Interpreter").
4. Open [`.vscode/launch.json`](.vscode/launch.json) — three configurations are provided:
   - **Backend: main.py** — runs `main.py` under the debugger with `.env` loaded
   - **Backend: attach to uvicorn** — attach to a process started with `debugpy`
   - **Scripts: seed.py** — debug the seed script
5. Press `F5` or use the Run & Debug panel to start.

To attach to a running uvicorn process (useful when auto-reload is important):
```bash
pip install debugpy
python -m debugpy --listen 5678 --wait-for-client main.py
```
Then run the **"Backend: attach to uvicorn"** launch config.

### Backend — PyCharm

1. Open the project.
2. Go to **Run → Edit Configurations → +  → Python**.
3. Script path: `main.py`
4. Environment variables: click the folder icon and load `.env`
5. Working directory: project root
6. Click OK and press the debug button.

### Frontend — Chrome DevTools

Source maps are generated by Vite automatically in dev mode. Open Chrome DevTools (`F12`), navigate to the **Sources** tab, and find the `src/` directory under `localhost:3000`.

### Frontend — VSCode

Use the **"Frontend: Chrome"** launch config in `.vscode/launch.json`. Requires the Vite dev server to be running on port 3000.

---

## Docker Development Environment

The `docker-compose.dev.yml` provides a one-command dev environment with Xray included.

```bash
# Build and start (first time takes ~3 min to download Xray)
docker compose -f docker-compose.dev.yml up --build

# Start in background
docker compose -f docker-compose.dev.yml up -d

# Watch logs
docker compose -f docker-compose.dev.yml logs -f

# Stop
docker compose -f docker-compose.dev.yml down

# Full reset (delete volume with DB)
docker compose -f docker-compose.dev.yml down -v
```

The Docker setup:
- Mounts the source tree at `/code` — code changes trigger auto-reload
- Runs `alembic upgrade head` and `scripts/seed.py` on every start
- Maps port 8000 (API/dashboard) and 3000 (Vite dev server)
- Uses Xray installed in the image (`XRAY_ENABLED=True` inside Docker)
- Stores the SQLite DB in a named volume (`marzban-dev-data`)

---

## Health Check Checklist

Verify the environment is ready by checking all of these:

### Backend
- [ ] `python main.py` starts without errors
- [ ] http://127.0.0.1:8000/docs loads Swagger UI
- [ ] `GET /api/core` returns `200`
- [ ] Scheduler starts (`APScheduler started` in logs)

### Frontend
- [ ] http://127.0.0.1:8000/dashboard/ loads the login page
- [ ] Login with `admin` / `admin123` succeeds
- [ ] User list shows the 5 seed users
- [ ] Creating / editing / deleting a user works

### Database
- [ ] `alembic upgrade head` runs without errors
- [ ] `alembic current` shows the latest revision
- [ ] `python scripts/seed.py` is idempotent (re-run → all `[skip]` lines)

### CLI
- [ ] `python marzban-cli.py admin list` shows `admin` and `testadmin`
- [ ] `python marzban-cli.py user list` shows the 5 seed users

---

## Troubleshooting

### `FileNotFoundError: [Errno 2] No such file or directory: '/usr/local/bin/xray'`

Set `XRAY_ENABLED=False` in `.env`. The app will start without launching the Xray core.

### `ModuleNotFoundError: No module named 'decouple'`

Run:
```bash
pip install -r requirements.txt
```

### Port 8000 already in use

```bash
# Find what is using it
lsof -i :8000

# Kill it
kill -9 $(lsof -ti :8000)
```

### `UNIQUE constraint failed: admins.username`

The seed script is idempotent — this should never happen. If it does, the DB is corrupted. Reset:
```bash
rm -f dev.sqlite3 && alembic upgrade head && python scripts/seed.py
```

### Frontend shows blank page after login

The built dashboard (`app/dashboard/build/`) may be stale. With `DEBUG=True` this doesn't matter because the Vite dev server is used. If you see a blank page in production mode:
```bash
cd app/dashboard && npm run build && cd ../..
```

### Alembic `Can't locate revision` error

Your DB is on a migration that no longer exists (usually after a branch switch). Reset:
```bash
rm -f dev.sqlite3 && alembic upgrade head && python scripts/seed.py
```

### `npm ERR! Missing script: gen:theme-typings`

Run `npm install` inside `app/dashboard/` first. The `postinstall` script generates Chakra theme typings.

---

## Project Structure (quick reference)

```
Marzban/
├── main.py                    # Entry point — starts uvicorn
├── config.py                  # All env-var settings (python-decouple)
├── .env.development           # Dev environment template
├── .env                       # Active config (git-ignored)
├── xray_config.json           # Xray inbound/outbound config
├── alembic.ini                # Alembic migration config
├── requirements.txt           # Python dependencies
├── scripts/
│   └── seed.py                # Dev data bootstrap
├── app/
│   ├── __init__.py            # FastAPI app, APScheduler, CORS
│   ├── db/
│   │   ├── base.py            # SQLAlchemy engine + session
│   │   ├── models.py          # ORM models (single source of truth)
│   │   ├── crud.py            # All DB operations
│   │   └── migrations/        # Alembic migration scripts
│   ├── models/                # Pydantic schemas (request/response)
│   ├── routers/               # FastAPI route handlers
│   ├── jobs/                  # APScheduler background tasks
│   ├── xray/                  # Xray subprocess + gRPC management
│   └── dashboard/             # React + TypeScript frontend
│       ├── src/               # Frontend source
│       ├── vite.config.ts     # Vite config (includes dev proxy)
│       └── package.json
├── cli/                       # CLI commands (typer)
├── .vscode/
│   └── launch.json            # VSCode debug configurations
├── docker-compose.yml         # Production Docker Compose
└── docker-compose.dev.yml     # Development Docker Compose
```

---

## Workflow Summary

```
Day 1 — first time setup:
  pip install -r requirements.txt
  cd app/dashboard && npm install && cd ../..
  cp .env.development .env
  alembic upgrade head
  python scripts/seed.py
  python main.py

Daily development:
  python main.py           ← starts backend + Vite dev server

After pulling new migrations:
  alembic upgrade head

Reset everything:
  rm -f dev.sqlite3
  alembic upgrade head
  python scripts/seed.py
```
