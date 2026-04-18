# pfSense Configuration Backup

Backs up configuration from one or more pfSense instances on a schedule, stores
the XML on disk, and serves a web dashboard behind Traefik (OIDC-authenticated)
to monitor, trigger, schedule, and compare backups.

## Architecture

Two containers in one compose stack, sharing a SQLite database and (for the worker)
the backup directory:

```
Browser ── HTTPS ──► Traefik ──► web (FastAPI + React SPA)
                                   │ HTTP (REST + WS /api/events)
                                   │
                                   │ ZeroMQ PUSH :5555 ──► worker
                                   └─ ZeroMQ SUB :5556 ◄── (commands + events)
                                   │
                                   └── SQLite (WAL) ◄──► worker
                                          /app/data/app.db
                                          /app/data/secret.key   (Fernet key)

Worker writes pfSense config XML → /backups
Worker exposes Prometheus metrics → :8000/metrics
```

- **worker** — APScheduler cron runner + backup executor. Loads `Instance` rows
  from the DB, decrypts credentials with Fernet, logs into pfSense, POSTs to
  `/diag_backup.php`, writes XML to `/backups/<subfolder>/`, applies per-instance
  retention, and sends webhook notifications. Publishes events via ZMQ PUB.
- **web** — FastAPI + React SPA. Traefik terminates TLS; Authlib handles the
  OIDC flow with an email allowlist. Mutating endpoints are CSRF-protected
  (double-submit cookie). `/api/events` is a WebSocket bridged from the worker's
  ZMQ PUB stream.

## Features

- Multiple pfSense instances with per-instance cron schedules.
- Live dashboard: last backup, next run, events streamed as they happen.
- Trigger backups and connection tests on demand.
- Browse, download (single or zip), and diff backups (Monaco side-by-side XML).
- Webhook notifications — Discord, Healthchecks, or arbitrary JSON.
- OIDC login with an allowlist.
- Prometheus metrics (`:8000/metrics`) on the worker.
- Audit log of every mutation.

## Requirements

- Docker + Docker Compose.
- An OIDC provider (e.g., Authelia, Keycloak, Google) that you can register a
  client with. The only scopes needed are `openid email profile`.
- Traefik already running on a reachable `traefik` docker network (or edit
  `compose.yaml` to suit your reverse proxy).

## Deployment

```bash
# 1. Clone
git clone git@github.com:metril/pfsense-backup.git
cd pfsense-backup

# 2. Configure environment
cp .env.example .env
# ...edit .env (SESSION_SECRET, OIDC_*, OIDC_ALLOWED_EMAILS, WEB_HOST).

# 3. Ensure volumes exist with correct ownership (uid 1000 in the image)
sudo install -d -o 1000 -g 1000 ./data
sudo install -d -o 1000 -g 1000 /mnt/usb-hdd-mirror/backups/pfsense

# 4. Pull published images (production)
docker compose -f compose.yaml -f compose.prod.yaml pull
docker compose -f compose.yaml -f compose.prod.yaml up -d

# 4-alt. Or build locally from source (development)
docker compose build
docker compose up -d
```

### First-run setup via the UI

1. Visit `https://${WEB_HOST}`; you'll be redirected to your OIDC provider.
2. After login, open **Instances → Add instance**. Fill in:
   - Name, URL (`https://…`), username, password (stored Fernet-encrypted).
   - Subfolder (for organizing files under `/backups/`), backup prefix.
   - SSL verify, timeout, retention count, compression.
   - Cron expression (the Build… button helps) + timezone.
3. Click **Test Connection** to verify credentials. The event feed shows the
   result.
4. Click **Backup Now** to run a one-off backup. On success a file appears in
   `/backups/<subfolder>/` and a `Backup` row appears in the DB (visible from
   the Backups page).
5. Add webhook notifications from **Notifications**. Each webhook has a
   `trigger` (always / success / failure), optional custom headers, and an
   optional payload template (for Slack-like services that require specific
   JSON shapes).

### Migrating from the legacy `config.yaml`

The pre-v0.1.0 version of this tool read `config/config.yaml` at container
startup. That file is now **gitignored** (see `config/config.yaml.example`)
and is **not read** by the application — the database is the source of truth.
To migrate:

1. Keep your `config/config.yaml` file around (it's still on disk, just not
   tracked by git).
2. After first login to the new UI, re-enter each instance using the values
   from `config.yaml`. The UI stores passwords encrypted at rest.
3. Re-add each webhook from the Notifications page.
4. Once you've verified backups still run, the YAML file can be deleted.

## Backing up the app database

`./data/app.db` + `./data/secret.key` are the crown jewels — without them, the
encrypted pfSense credentials are unrecoverable.

**Back up the entire `./data/` directory off-site.** One hourly `rsync` or
`restic` job is enough.

## Security notes

- pfSense credentials are encrypted with Fernet at rest (`Crypto` class in
  `pfsense_shared/crypto.py`). The key is generated on first boot with 0600
  permissions.
- Rotating `SESSION_SECRET` invalidates all existing browser sessions.
  Rotating the Fernet key (`PFSENSE_BACKUPS_SECRET_KEY_FILE`) invalidates all
  stored passwords — they'll need to be re-entered in the UI.
- Restore (uploading a backup **back** to pfSense) is intentionally not
  implemented; it's high-risk to do over the same form auth, and manual
  restore via the pfSense web UI is safer.

## Development

Python: `uv sync --extra worker --extra web --extra dev` then
`uv run ruff check …`, `uv run mypy …`, or `uv run python -m worker`.

Frontend: `cd frontend && npm install && npm run dev`. Vite proxies `/api`
and `/api/events` to `http://localhost:8080`.

Releases are cut by pushing a semver tag (`v0.1.0`). GitHub Actions builds
multi-arch images to `ghcr.io/metril/pfsense-backup-{worker,web}` and opens
a GitHub Release with auto-generated notes.

### Mirroring to both GitLab and GitHub

Local commits go to GitLab (`origin`) with the developer's local git identity.
`scripts/push-github.sh` runs `git filter-repo --mailmap` against an
ephemeral clone to rewrite authors/committers to the `metril` identity and
force-pushes to GitHub. See `scripts/github-mailmap.txt.example` for the
mailmap format.

## Endpoints (summary)

| Path | Purpose |
|---|---|
| `GET /api/health` | liveness + worker_alive probe |
| `GET /api/auth/{login,callback,me,logout,csrf,status}` | OIDC flow |
| `GET/POST /api/instances` & `GET/PUT/DELETE /api/instances/{id}` | CRUD |
| `POST /api/instances/{id}/{test-connection,backup-now}` | trigger |
| `GET /api/schedule`, `PUT /api/schedule/{id}` | per-instance cron |
| `GET /api/schedule/_tools/preview` | live cron validation |
| `GET /api/backups` | history listing |
| `GET /api/backups/{id}/{content,download}` | single-file access |
| `POST /api/backups/download-zip` | multi-file bundle |
| `GET /api/backups/diff/pair?a=&b=` | two backups' content for Monaco |
| `GET/POST /api/notifications` & `/{id}` + `/test` | webhook CRUD |
| `GET/PUT /api/settings{,/backup,/logging}` | global file-layout + logging |
| `GET /api/jobs`, `/{id}` | job history |
| `WS  /api/events` | live worker events stream |
| `GET :8000/metrics` | Prometheus (worker side) |
