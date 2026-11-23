# CommonGround — Global Community Discussion Platform

A community discussion platform built with **React 19 + TypeScript + Vite** and **Python + Django REST Framework + Django Channels**. SQLite is the default for a quick local start; PostgreSQL and Redis are supported for persistent and multi-worker deployments.

## What is implemented

**Accounts**
- Registration, login, token refresh and logout. The short-lived access JWT (10 minutes) is held in memory only; the refresh token lives in an HttpOnly cookie scoped to `/api/v1/auth/`, rotated on use and blacklisted after rotation. Login, refresh, logout and register require a CSRF token.
- Current-user and extended profile endpoints (bio, country, language, interests, avatar URL, website).
- **Account security** (`/settings/security`): email is required at sign-up and unique (any case). A confirmation link is emailed at registration, and a banner reminds unconfirmed users. "Forgot password?" emails a reset link that works for 1 hour and only once; the answer is the same whether or not the account exists. Change password needs the current one and signs out every other device. Change email needs the password, and the address changes only after the new inbox confirms it (the old inbox gets a notice). "Sign out other devices" and "Sign out everywhere" are also on that page. Revocation rejects refresh **and access** tokens issued before it, and a "your password was changed" alert email is sent.

**Communities**
- Public, restricted and private communities. Public communities are joined instantly; restricted ones create a membership request that moderators approve or reject; private ones are invitation-only.
- Member roles (owner/admin/moderator/member), role changes, member removal, community rules and pinned announcements.
- New communities start as **pending** and only appear once a site admin approves them in Django admin (admins can also reject, suspend and restore).

**Discussions**
- Threads with rich text (sanitised server-side with `bleach`), categories, trending and search.
- Comments with one-level nested replies, reactions, bookmarks.
- File attachments; attachments in non-public communities are only downloadable by active members.

**Messaging (real time)**
- Direct and group conversations, member management, read receipts.
- Live delivery and online presence over WebSockets.

**Notifications (real time)**
- Stored notifications pushed live over WebSockets, unread counts, mark-read, and per-user preferences by category.

**People & social**
- Follow / unfollow, follower and following lists, and Instagram-style public profiles at `/u/<username>`: cover, avatar, discussion/follower/following counts, bio, location, website, interests.
- Floating profile cards: hover over (or keyboard-focus) any member's name to preview their profile, then follow, message or open it.
- People page (`/people`): search by name or username, plus "People you may know" with a reason (in your contacts, follows you, followed by people you follow, shared community).
- Connection badges: *Mutual*, *Follows you*, *In your contacts*, *Followed by …*, and private relation labels only you can see (Family, Friend, Colleague, Classmate, Neighbour, Other).
- Find friends from contacts: Android Chrome's contact picker, a `.vcf` contacts file (any device) or typed numbers. Contacts are matched once and **not stored**; only members who switched on "Let people who have my number or email find me" can be found. Phone numbers are optional, private, never shown, and matched via a keyed hash.
- Facebook, Instagram and TikTok do not let other sites read follower lists, so connections come from CommonGround itself and your contacts.

**Notification alerts**
- A short chime plus a system pop-up (when the tab is in the background) for each live notification, an unread count in the tab title, and on/off switches under Notification preferences. Browsers only allow sound after the first click or tap on the site.

**Polls, video posts and Reels**
- Polls on posts (2–6 options, single or multiple choice, 1 hour to 1 week). Results stay hidden until you vote, except for the author and once the poll closes. You can change or take back your vote.
- Video posts up to 3 minutes / 100 MB (MP4, MOV, WebM). The browser captures the cover frame. Videos stream with HTTP Range requests over signed links, autoplay muted when on screen, and load nothing until near the screen. `/reels` is a full-screen, swipe-up video feed.

**Moderation**
- `/moderation` for site staff and community moderators: reports grouped by post, comment, story, message or account, with reasons and details. Staff can dismiss, remove, warn, suspend (1–365 days) or ban. Community owners, admins and moderators can dismiss or remove posts and comments in their own communities.
- The person is told why. Reporters hear back. Every decision goes into an audit log with a copy of the removed content, and staff can look up an account and lift a suspension or ban. Suspended people see the reason and end date when they sign in.

**Voice and video calls**
- One-to-one WebRTC calls from any direct chat: ringing on every open tab (answering in one stops the others), mute, camera on/off, a call timer, and a "📞 Video call · 2:31" or "Missed call" line in the chat. Media goes directly between the two browsers; the server only relays the call setup. Calls across different networks need a TURN server (see `docs/DEPLOY.md`).

**Events**
- Community events with RSVPs, attendee lists, cancellation, a calendar view, and reminders sent by a scheduled management command.

**Money and growth**
- **Tips**: members tip a post or its author from the post's ⋯ menu or the *Tip* button, paying with M-Pesa, Mixx by Yas (Tigo Pesa), Airtel Money, HaloPesa or a card on Flutterwave's hosted page. The creator gets 90% (`TIP_PLATFORM_FEE_PERCENT`), sees it on `/earnings` and asks for a payout to mobile money, which staff send and mark paid in Django admin.
- **Sponsored posts**: a member promotes one of their public posts for 1–30 days (`PROMOTION_DAILY_PRICE` per day). After a staff review it appears in other members' *For you* feed marked "Sponsored", with view and click counts for the advertiser. A rejected promotion is refunded as ad credit.
- **Referral rewards**: each member's invite link (`/register?invite=<username>`) earns them ad credit when the friend confirms their email, with WhatsApp/Facebook/X sharing and a monthly top-inviters list.
- **Search engines and link previews**: public discussions and communities can be read signed out, with server-filled titles, descriptions, Open Graph cards and schema.org data, plus `/sitemap.xml` and `/robots.txt`.
- Payments are confirmed with the gateway, never from the browser, and every balance change is a ledger entry. Set-up: `docs/DEPLOY.md`, "Payments".

**Admin**
- Branded Django admin with a dashboard of platform stats and community approval actions.

## Not implemented yet

Group calls, push notifications to closed apps (pop-ups need an open tab), two-factor sign-in, server-side video transcoding (videos are stored as uploaded), file virus scanning, and analytics.

## Requirements

- Python 3.11 or newer (developed on 3.14).
- Node.js 20 or newer, and npm.
- Optional: Docker and Docker Compose for PostgreSQL/Redis.

## 1. Configuration (.env)

`backend/config/settings.py` automatically loads a `.env` file from `backend/.env` and then the project root `.env`. Real environment variables always take priority over `.env` values. `.env` files are git-ignored.

```bash
cp .env.example .env   # then edit as needed
```

With no `.env` at all, the app runs on SQLite with an in-memory channel layer and cache, accepting `localhost` / `127.0.0.1` only.

**Testing from a phone or another device on your network:** add your machine's LAN IP to `DJANGO_ALLOWED_HOSTS`, and the matching Vite origin (for example `http://192.168.1.20:5173`) to both `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS`.

### Contacts on phones

The browser contact picker only exists in **Chrome on Android** and only on **HTTPS** (or `localhost`). To try it from a phone against the dev server at `http://<your-LAN-IP>:5173`, open `chrome://flags/#unsafely-treat-insecure-origin-as-secure` on the phone, add that address, and relaunch Chrome. Everywhere else, use the `.vcf` import. In production, serve the site over HTTPS.

`DEFAULT_PHONE_COUNTRY_CODE` (default `255`, Tanzania) is applied to local numbers such as `0712…`.

### Rate limits

The API rate-limits clients: `THROTTLE_ANON_RATE` (default 1000/hour) for signed-out requests, `THROTTLE_USER_RATE` (5000/hour) for signed-in users, `THROTTLE_AUTH_RATE` (10/minute per IP) for login, registration, password-reset confirmation and email confirmation, `THROTTLE_ACCOUNT_EMAIL_RATE` (5/hour) for requests that send email (password reset, confirmation resend, email change), and `THROTTLE_CONTACTS_RATE` (20/hour) for contact matching. Blocked requests get HTTP 429 with a `Retry-After` header, and the UI shows "Too many attempts. Please wait N minutes".

Set `NUM_PROXIES` to the number of reverse proxies in front of Django (1 for the Vite dev server, which forwards the client IP). With the wrong value, all visitors share one limit (too low) or clients can forge their IP (too high). Counters live in the cache, so restarting a server that has no Redis clears them.

### Emails (password reset, confirmation)

In development (`DJANGO_DEBUG=True`) emails are not sent. Each one is saved as a file in `backend/sent_emails/`, so open the newest file there to get the link. Links point at `FRONTEND_URL` (default `http://localhost:5173`; use your LAN address, e.g. `http://192.168.1.20:5173`, when testing from a phone). For real delivery set `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` with `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` and `DEFAULT_FROM_EMAIL`. Production refuses to start without an `https://` `FRONTEND_URL` and an `EMAIL_HOST` when SMTP is used.

## 2. Backend setup (Ubuntu/Linux)

From the project root:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

`daphne` is installed as a Django app, so `runserver` serves both HTTP and WebSockets. The API is at `http://127.0.0.1:8000/api/v1/` and Django admin at `http://127.0.0.1:8000/admin/`. Use `python manage.py runserver 0.0.0.0:8000` to accept connections from other devices.

### Event reminders

Reminders are sent by a management command that should run every few minutes, for example from cron:

```cron
*/5 * * * * cd /path/to/backend && .venv/bin/python manage.py send_event_reminders >> event_reminders.log 2>&1
```

## 3. Frontend setup

In a second terminal, from the project root:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The Vite dev server proxies `/api` and `/ws` to the backend on `127.0.0.1:8000`, so no extra configuration is needed. To point the frontend at a different API, set `VITE_API_URL` in `frontend/.env` and restart Vite.

## 4. Optional PostgreSQL + Redis

```bash
docker compose up -d db redis
```

Then add to `.env`:

```env
DATABASE_URL=postgresql://community_user:community_password@127.0.0.1:5432/community_db
REDIS_URL=redis://127.0.0.1:6379/0
```

and run `python manage.py migrate`. `REDIS_URL` backs both the Channels layer and the cache that holds WebSocket tickets, so it is required when running more than one backend worker.

## 5. Running tests

```bash
cd backend && .venv/bin/python manage.py test   # Django tests
cd frontend && npm test                          # Vitest + React Testing Library
cd frontend && npx tsc --noEmit                  # type check
```

Backend tests run with a temporary `MEDIA_ROOT` (see `config/test_runner.py`), so uploads made by tests never land in `backend/media/`.

## 6. API overview

All endpoints are under `/api/v1/`. List endpoints use DRF pagination (`{ "count", "next", "previous", "results" }`) and support `?search=` and `?ordering=` where relevant. Full request/response examples are in [`docs/`](docs/).

| Area | Endpoints |
|---|---|
| Auth | `POST auth/register/`, `GET auth/csrf/`, `POST auth/token/` (login), `POST auth/token/refresh/`, `POST auth/logout/`, `POST auth/ws-ticket/`, `GET/PATCH auth/me/` (email is read-only here), `GET/PATCH auth/profile/` |
| Posts | `POST posts/` (photos), `POST posts/video/`, `POST posts/poll/`, `POST/DELETE discussions/{id}/vote/`, `GET videos/{id}/?t=` (signed, Range), `GET discussions/?media=photos|videos|polls` |
| Moderation | `GET moderation/queue/`, `POST moderation/decisions/`, `GET moderation/log/`, `GET moderation/accounts/{username}/`, `POST moderation/accounts/{username}/restore/` |
| Calls | `POST calls/`, `GET calls/active/`, `POST calls/{id}/accept|decline|end/`; signalling on `ws/calls/` |
| Ops | `GET health/` (database + cache check for load balancers) |
| Account security | `POST auth/password/reset/` `{login}`, `POST auth/password/reset/confirm/` `{uid, token, new_password, new_password_confirm}`, `POST auth/password/change/` `{current_password, new_password, new_password_confirm}`, `POST auth/email/verify/` `{token}`, `POST auth/email/resend/`, `POST auth/email/change/` `{new_email, password}`, `POST auth/sessions/revoke/` `{keep_current}` |
| Communities | `communities/` (list/create), `communities/{id}/` (detail/update/delete), `join/`, `leave/`, `members/`, `membership-requests/`, `approve-request/`, `reject-request/`, `update-member-role/`, `remove-member/`, `rules/`, `rules/{rule_id}/`, `announcements/`, `announcements/{announcement_id}/` |
| Discussions | `discussions/` (list/create), `discussions/{id}/`, `trending/`, `categories/`, `bookmarked/`, `{id}/react/`, `{id}/bookmark/`, `{id}/comments/`, `{id}/attachments/`; `comments/`, `comments/{id}/`; `GET attachments/{id}/download/` |
| Messaging | `conversations/` (list/create), `conversations/start-direct/`, `conversations/{id}/`, `{id}/messages/`, `{id}/members/`, `{id}/add-members/`, `{id}/remove-member/`, `{id}/mark-read/`; `GET messaging/users/` (user search) |
| Notifications | `notifications/`, `unread-count/`, `mark-all-read/`, `{id}/mark-read/`, `DELETE notifications/{id}/`, `GET/PATCH notifications/preferences/` |
| Events | `events/` (list/create), `events/{id}/`, `{id}/rsvp/`, `{id}/attendees/`, `{id}/cancel/` |
| People | `GET people/?search=`, `GET people/suggestions/`, `POST people/contacts/match/` (`{phones: [], emails: []}`, max 2000, rate-limited), `GET people/{username}/`, `POST/DELETE people/{username}/follow/`, `GET people/{username}/followers/`, `GET people/{username}/following/`, `PUT/DELETE people/{username}/label/` |

### WebSockets

| Path | Purpose |
|---|---|
| `ws/chat/{conversation_id}/` | Messages in one conversation |
| `ws/presence/` | Online/offline presence |
| `ws/notifications/` | Live notifications |

WebSockets never receive the JWT. The client first calls `POST /api/v1/auth/ws-ticket/` and connects with `?ticket=<ticket>`. Tickets are single-use and expire after `WEBSOCKET_TICKET_TTL_SECONDS` (default 15).

## 7. First-use workflow

1. Create a superuser and register a normal account in the web UI.
2. Create a community, then approve it in Django admin (**Communities → approve**).
3. Open the community to post discussions, rules, announcements and events.
4. React, comment, reply, bookmark and attach files on discussions.
5. Open **Messages** to start a direct or group chat, and **Notifications** to see live updates.

## 8. Performance & scaling

Measured results, load-test numbers, and the scaling plan are in [`docs/SCALING.md`](docs/SCALING.md). Production server configs are in [`deploy/`](deploy/): `gunicorn -c ../deploy/gunicorn.conf.py config.asgi:application` from `backend/`, behind `deploy/nginx.conf`.

## 9. Production notes

**Full step-by-step guide: [`docs/DEPLOY.md`](docs/DEPLOY.md)** (server setup, `.env`, systemd, nginx with CSP, cron, TURN and a go-live checklist).


This project is not production-hardened as-is. Before deploying:

- Set `DJANGO_ENV=production`, `DJANGO_DEBUG=False` and a strong unique `DJANGO_SECRET_KEY`.
- Set `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS` to exact production values.
- Serve over HTTPS and set `REFRESH_COOKIE_SECURE=True` (use `REFRESH_COOKIE_SAMESITE=None` only for cross-site frontend/API deployments).
- Use managed PostgreSQL (`DATABASE_URL`) with backups and Redis (`REDIS_URL`).
- Serve uploaded media from storage with access control and add file scanning.
- Configure SMTP (or another email backend) and `FRONTEND_URL=https://…` so reset and confirmation links work.
- Add a moderator dashboard, CI, logging and monitoring.

## License

Project starter created for development. Add a license before distributing or commercializing it.
