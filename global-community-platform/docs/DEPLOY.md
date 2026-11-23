# Deploying CommonGround to production

This is the path that was tested: one Ubuntu server running nginx → gunicorn (uvicorn
workers) → Django, plus PostgreSQL, Redis and (for calls) coturn. Everything in
`deploy/` is a working template; replace `example.org` with your domain.

## What you must provide

| Item | Why | Notes |
|---|---|---|
| A domain + DNS | Links in emails, cookies, CSP | e.g. `commonground.example` → server IP |
| HTTPS certificate | Required: secure cookies, camera/mic access, service workers | Let's Encrypt via `certbot --nginx` |
| PostgreSQL 15+ | Main database (SQLite is for development only) | Managed DB recommended; set up daily backups |
| Redis 7+ | Shared cache, rate limits, WebSocket tickets, live messages | Production refuses to start without it |
| An email provider (SMTP) | Password reset, email confirmation, security alerts | e.g. Amazon SES, Postmark, Mailgun, Brevo |
| A TURN server | Calls between people on different networks | coturn on a small VM (see `deploy/turnserver.conf.example`) |
| A server | 2 vCPU / 4 GB RAM is a comfortable start | Scale out by adding app servers behind a load balancer |

## 1. Server setup

```bash
sudo apt install nginx postgresql redis-server python3-venv certbot python3-certbot-nginx
sudo useradd --system --home /srv/commonground commonground
sudo mkdir -p /srv/commonground /var/log/commonground && sudo chown commonground: /srv/commonground /var/log/commonground
# copy the project to /srv/commonground (git clone or rsync)
cd /srv/commonground/backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd /srv/commonground/frontend && npm ci && npm run build
```

## 2. Configuration (`/srv/commonground/.env`)

Start from `.env.example`. Required in production (the app refuses to start without them):

```ini
DJANGO_ENV=production
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=<python -c "import secrets; print(secrets.token_urlsafe(50))">
DJANGO_ALLOWED_HOSTS=commonground.example
CORS_ALLOWED_ORIGINS=https://commonground.example
CSRF_TRUSTED_ORIGINS=https://commonground.example
DATABASE_URL=postgresql://cg:<password>@127.0.0.1:5432/commonground
REDIS_URL=redis://127.0.0.1:6379/0
FRONTEND_URL=https://commonground.example
REFRESH_COOKIE_SECURE=True
NUM_PROXIES=1
MEDIA_ACCEL_REDIRECT_PREFIX=/protected-media/
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.your-provider.com
EMAIL_HOST_USER=...
EMAIL_HOST_PASSWORD=...
DEFAULT_FROM_EMAIL="CommonGround <no-reply@commonground.example>"
TURN_URLS=turn:turn.commonground.example:3478,turns:turn.commonground.example:5349
TURN_SECRET=<same as coturn static-auth-secret>
# Push notifications to closed apps (optional): run `manage.py generate_vapid_keys` once.
VAPID_PUBLIC_KEY=...
VAPID_PRIVATE_KEY=...
VAPID_SUBJECT=mailto:admin@commonground.example
# Encrypts authenticator-app (2FA) secrets. Optional; defaults to DJANGO_SECRET_KEY.
# Set it so the secret key can be rotated without switching off everyone's 2FA.
TWO_FACTOR_ENCRYPTION_KEY=<another long random string>
```

Keep `.env` readable only by the app user: `chmod 600 /srv/commonground/.env`.

## 3. Database, static files, first admin

```bash
cd /srv/commonground && deploy/manage.sh migrate
deploy/manage.sh collectstatic --noinput
deploy/manage.sh createsuperuser
deploy/manage.sh check --deploy        # must report no issues
```

## 4. Services

```bash
sudo cp deploy/commonground.service /etc/systemd/system/ && sudo systemctl enable --now commonground
sudo cp deploy/nginx.conf /etc/nginx/sites-available/commonground   # edit domain + connect-src
sudo ln -s /etc/nginx/sites-available/commonground /etc/nginx/sites-enabled/ && sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d commonground.example
crontab -u commonground deploy/crontab.example                      # reminders, story cleanup, token cleanup
```

Check: `curl https://commonground.example/api/v1/health/` → `{"status": "ok", ...}`.

### Background jobs, video conversion, upload scanning, group calls

- **Jobs** (event reminders, expired stories, pending video conversions, stale calls,
  token/session clean-up) run in a scheduler thread inside each web process when
  `SCHEDULER_ENABLED=True` (the default with `DJANGO_ENV=production`). A shared-cache
  lock makes each job run once per interval across all servers. Hosts without
  always-on processes can call `GET /api/v1/internal/tick/` (the repo's GitHub
  workflow `tick.yml` does it hourly). Set `CRON_SECRET` to require
  `Authorization: Bearer <secret>` on that endpoint (then the workflow needs it too).
  The crontab above still works and is harmless alongside the scheduler.
- **Videos** are re-encoded to H.264/AAC MP4 (max 1280 px, 30 fps, metadata stripped)
  by the ffmpeg bundled in the `imageio-ffmpeg` package; no system ffmpeg needed.
  `VIDEO_TRANSCODE=thread|sync|off`, `VIDEO_TRANSCODE_MAX_SIDE`, `VIDEO_TRANSCODE_TIMEOUT`.
  The original plays until the conversion finishes; files ffmpeg can't decode are deleted.
- **Document uploads** (PDF/DOC/DOCX/TXT) are checked for disguised files, scripts in
  PDFs, Word macros, embedded objects and remote templates. For full anti-virus,
  run ClamAV (`apt install clamav-daemon`) and set `CLAMD_SOCKET=/var/run/clamav/clamd.ctl`
  (or `CLAMD_HOST`/`CLAMD_PORT`). If clamd is configured but down, uploads are refused
  unless `CLAMD_FAIL_OPEN=True`.
- **Group calls** (group chats) are peer-to-peer meshes, capped by
  `GROUP_CALL_MAX_PARTICIPANTS` (default 8). Each person uploads one stream per
  participant, so large video calls need good upload bandwidth; TURN matters here too.

## 5. Go-live checklist

- [ ] `deploy/manage.sh check --deploy` shows no issues
- [ ] `/api/v1/health/` returns 200 and is watched by an uptime monitor
- [ ] Register a new account: the confirmation email arrives and its link works
- [ ] "Forgot password" email arrives and the reset works
- [ ] Two phones on **different networks** (e.g. Wi-Fi and mobile data) can make a video call (needs TURN)
- [ ] Upload a photo post, a video post and a story from a phone
- [ ] A staff account opens `/moderation`; a report from another account appears there
- [ ] Database backups run daily and a restore was tested
- [ ] `media/` (uploads) is backed up too
- [ ] Error logs are collected (`journalctl -u commonground`); consider Sentry
- [ ] Only ports 80/443 (and coturn's ports) are open in the firewall

## Updating

```bash
cd /srv/commonground && git pull
backend/.venv/bin/pip install -r backend/requirements.txt
deploy/manage.sh migrate && deploy/manage.sh collectstatic --noinput
(cd frontend && npm ci && npm run build)
sudo systemctl reload commonground
```

## Scaling notes

- Each app worker keeps up to `DB_POOL_MAX_SIZE` (default 10) PostgreSQL connections;
  keep `workers × servers × DB_POOL_MAX_SIZE` below PostgreSQL's `max_connections`
  (or put PgBouncer in front).
- More traffic: add app servers behind a load balancer; they share PostgreSQL and Redis.
  Uploaded media must then live on shared storage (NFS or S3-compatible) instead of local disk.
- See `docs/SCALING.md` for measured numbers.

## Free test deployment (Vercel + Supabase)

For trying CommonGround online at no cost; not for real users.

- **Vercel** (Hobby, free) runs `global-community-platform/Dockerfile.vercel` as a
  container: the React app, the API and WebSockets on one `*.vercel.app` address.
  It scales to zero after 5 minutes idle (the next visit cold-starts), WebSocket
  connections are closed after 5 minutes (the app reconnects automatically), and
  request bodies are capped at 4.5 MB, so large video uploads fail.
- **No Redis needed:** `CHANNEL_LAYER=postgres` keeps the shared cache (WebSocket
  tickets, rate limits) in a database table and delivers live events between
  instances with PostgreSQL LISTEN/NOTIFY (`channels_postgres`). With Redis available
  (e.g. Upstash), set `REDIS_URL` and `CHANNEL_LAYER=pubsub` instead.
- **Supabase** (free): Postgres in a dedicated `commonground` schema used by its own
  `commonground` role, plus the private `commonground-media` storage bucket, reached
  through the Vercel Supabase integration's `SUPABASE_URL` and
  `SUPABASE_SERVICE_ROLE_KEY` with `SUPABASE_STORAGE_BUCKET=commonground-media` (no S3
  keys). Uploaded files are served through short-lived signed links from Supabase.
- No email provider: reset/confirmation emails are printed in the runtime logs.
  No TURN server: calls work on the same network, often not across networks.

Project settings: root directory `global-community-platform`, and environment
variables `PORT=8000`, `DJANGO_ENV=production`, `DJANGO_DEBUG=False`,
`DJANGO_SECRET_KEY`, `DATABASE_URL` (Supabase session pooler, `commonground` role),
`SUPABASE_STORAGE_BUCKET`, `EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend`,
`CHANNEL_LAYER=postgres`, `DB_POOL_MAX_SIZE=3`, `CHANNELS_DB_POOL_MAX_SIZE=2` (the free
Supabase pooler has about 15 sessions in total), `NUM_PROXIES=1`, `FORWARDED_ALLOW_IPS=*`,
`WEB_CONCURRENCY=1`. Hosts and origins default to the Vercel domain.
Live at https://commonground-pearl.vercel.app (health: `/api/v1/health/`).

Push notifications: add `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` and `VAPID_SUBJECT`
(from `python manage.py generate_vapid_keys`; keep the same keys afterwards, or every
device must turn push on again). Without them the "Push notifications on this device"
switch says push isn't set up. On iPhone/iPad, push works only after "Add to Home Screen".

Two-step sign-in: if someone loses both their phone and recovery codes, a staff member
deletes their row under Admin → Two factor auths; they then sign in with the password.

To make an account staff (for `/moderation` and `/admin/`), run in Supabase's SQL
editor: `update commonground.auth_user set is_staff = true, is_superuser = true where username = '<you>';`
