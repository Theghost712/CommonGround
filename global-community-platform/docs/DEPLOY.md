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

## Free test deployment (Render + Supabase)

For trying CommonGround online at no cost. Not for real users: the free server
sleeps after 15 minutes without visitors (the next visit waits ~1 minute) and has
512 MB RAM, and Supabase pauses a free project after a week without traffic.

How it is wired (`render.yaml` at the repository root):

- **Render web service** (Docker, free): the React app, the API and WebSockets on one
  `https://<name>.onrender.com` address. Migrations run on every start.
- **Render Key Value** (free Redis, 25 MB): cache, rate limits, WebSocket tickets, live events.
- **Supabase** (free): Postgres in a dedicated `commonground` schema, used by its own
  `commonground` role, and a private `commonground-media` storage bucket. Uploaded
  photos and videos are served through short-lived signed links straight from Supabase.
- No email provider: reset and confirmation emails are printed in Render's **Logs** tab.
- No TURN server: calls work on the same network, often not between mobile data and Wi-Fi.
- No cron on the free plan: event reminders aren't sent and expired story files stay
  in storage (expired stories are still hidden).

Steps:

1. Push this repository to GitHub (a private repository is fine).
2. Supabase dashboard → Project Settings → Storage → **S3 access keys** → New key.
3. Render dashboard → New → **Blueprint** → connect the repository. When asked, paste
   `DATABASE_URL`, `S3_ACCESS_KEY_ID` and `S3_SECRET_ACCESS_KEY`.
4. Wait for the first deploy (~5–10 minutes), then open the `.onrender.com` address
   and register. To make an account staff (for `/moderation` and `/admin/`), run in
   Supabase's SQL editor: `update commonground.auth_user set is_staff = true, is_superuser = true where username = '<you>';`
