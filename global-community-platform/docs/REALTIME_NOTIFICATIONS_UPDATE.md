# CommonGround — Real-Time Notifications Module

This incremental update adds persistent in-app notifications, a JWT-authenticated WebSocket stream, unread counts, per-category preferences, and a React notifications centre.

## Implemented events

- New private/group chat message.
- Discussion comment and nested reply.
- Discussion reaction.
- `@username` mention in a discussion, comment, or chat message.
- Restricted-community membership request to active owners and admins.
- Membership request approval.
- New community announcement to active members.

Community invitations, follower notifications, browser push notifications, and scheduled live-session reminders require their own workflow/integration and are not represented as completed in this update.

## Backend setup

The app is registered as `apps.notifications`. Existing Channels JWT middleware is reused for `ws/notifications/`.

From `backend/` with your existing virtualenv active:

```bash
python manage.py check
python manage.py makemigrations notifications
python manage.py migrate
python manage.py test apps.notifications
```

The API endpoints are:

- `GET /api/v1/notifications/` — current user's notifications (paginated); supports `?unread=true`.
- `GET /api/v1/notifications/unread-count/` — unread count.
- `POST /api/v1/notifications/mark-all-read/` — mark all current user's notifications as read.
- `POST /api/v1/notifications/{id}/mark-read/` — mark one notification as read.
- `DELETE /api/v1/notifications/{id}/` — delete one of the current user's notifications.
- `GET/PATCH /api/v1/notifications/preferences/` — read/update notification categories.
- `ws://localhost:5173/ws/notifications/?token=<JWT access token>` — proxied by Vite to Django ASGI.

## Frontend setup

Restart Django and Vite. Open:

- `http://localhost:5173/notifications`
- `http://localhost:5173/notifications/preferences`

A notification badge appears in the left navigation. The WebSocket reconnects with backoff and the unread total is refreshed periodically as a fallback.

## Notification preferences

Users can enable or disable message, discussion, community, mention, and system notification categories. A disabled category prevents new notification records from being created for that category.

## Notes

- The Vite `/ws` proxy must have `ws: true`.
- InMemoryChannelLayer supports local single-process development. Use Redis (`REDIS_URL`) when running multiple processes or deploying.
- WebSocket JWT is passed as a query parameter for local development, consistent with the existing chat implementation. Use short-lived WebSocket tickets or secure cookie auth in production.
- In-app real-time updates do not equal browser push notifications. Browser/mobile push needs a service worker and notification permission flow.
