# Notifications API Examples

Base URL: `/api/v1/`. All endpoints below require `Authorization: Bearer <access_token>` except WebSocket connection authentication uses the query-string token in local development.

## List notifications

`GET /notifications/`

Optional query parameters:
- `unread=true` — only unread notifications.
- `unread=false` — only read notifications.
- `type=message` — filter by notification type.

Response is paginated using the project's DRF pagination settings.

## Unread count

`GET /notifications/unread-count/`

```json
{ "unread_count": 3 }
```

## Mark one notification as read

`POST /notifications/24/mark-read/`

```json
{
  "notification": {
    "id": 24,
    "notification_type": "message",
    "title": "New message from alex",
    "body": "Hello there",
    "target_url": "/messages?conversation=8",
    "is_read": true
  },
  "unread_count": 2
}
```

## Mark all as read

`POST /notifications/mark-all-read/`

```json
{ "marked_read": 3, "unread_count": 0 }
```

## Notification preferences

`GET /notifications/preferences/`

`PATCH /notifications/preferences/`

```json
{
  "messages_enabled": true,
  "discussions_enabled": true,
  "communities_enabled": true,
  "mentions_enabled": true,
  "system_enabled": false
}
```

## WebSocket

`ws://localhost:5173/ws/notifications/?token=<access_token>`

The Vite development server proxies `/ws` to Django's ASGI server. A new notification event has this structure:

```json
{
  "type": "notification.new",
  "notification": {
    "id": 24,
    "notification_type": "message",
    "title": "New message from alex",
    "body": "Hello there",
    "target_url": "/messages?conversation=8",
    "is_read": false
  },
  "unread_count": 3
}
```
