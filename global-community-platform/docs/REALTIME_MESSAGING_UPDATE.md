# CommonGround — Real-Time Messaging Update

This incremental update adds private and group chat to the existing CommonGround React + Django REST Framework project.

## Included

### Backend
- New `apps.messaging` Django application.
- Direct and group conversation records.
- Conversation membership and group owner/admin roles.
- Persistent messages in the existing database.
- Per-user message read receipts and unread counts.
- User search for starting a conversation.
- REST endpoints for listing conversations, starting direct chats, creating group chats, listing/sending messages, marking a conversation read, and group participant management.
- Django Channels WebSocket consumer authenticated with JWT.
- WebSocket events for message delivery, typing indicators, presence updates, and read receipts.
- Basic per-WebSocket message rate limiting.
- Active-membership re-checks on incoming WebSocket events and connection revocation when a group member is removed.
- Django Admin registrations and backend tests.

### Frontend
- Replaces the placeholder Messages page with a functional chat interface.
- Search existing conversations.
- Search users and start private chats.
- Create group conversations.
- Live message updates, typing indicators, online presence events, unread counts, and read status.
- REST fallback when the WebSocket is not connected.
- Vite proxy for `/ws` WebSocket requests.

## Apply the update to an existing project

Extract this ZIP into the existing `global-community-platform` project root, not inside `backend` or `frontend`:

```bash
cd ~/CommunityTalk/global-community-platform
unzip -o ~/Downloads/commonground-realtime-messaging-update.zip -d .
```

Install the updated backend requirements (Daphne is added so Django's `runserver` serves the ASGI application):

```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt
python manage.py makemigrations messaging
python manage.py migrate
python manage.py check
python manage.py test apps.messaging
```

Start the backend:

```bash
python manage.py runserver 127.0.0.1:8000
```

In a second terminal, restart Vite so it loads the WebSocket proxy:

```bash
cd ~/CommunityTalk/global-community-platform/frontend
npm install
npm run dev
```

Open `http://localhost:5173/messages` while signed in.

## Local channel layer and Redis

The existing Django settings use `InMemoryChannelLayer` when `REDIS_URL` is not configured. That is suitable for a single local development process, but it does not share events between multiple ASGI worker processes.

For shared channel events, start the Redis service from the project's Docker Compose file:

```bash
docker compose up -d redis
```

Set the Redis URL in the same shell/environment used to start Django:

```bash
export REDIS_URL=redis://127.0.0.1:6379/0
```

Then restart Django. Redis is recommended for production and multi-worker deployments.

## REST API

All endpoints require JWT authentication except the token endpoint used by the existing authentication module.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/messaging/users/?q=al` | Search users by username or name |
| GET | `/api/v1/conversations/` | List the signed-in user's conversations |
| POST | `/api/v1/conversations/start-direct/` | Start or retrieve a direct conversation; body: `{"user_id": 12}` |
| POST | `/api/v1/conversations/` | Create a group; body: `{"title":"Project team","member_ids":[12,13]}` |
| GET | `/api/v1/conversations/{id}/messages/` | Get up to the latest 100 messages |
| POST | `/api/v1/conversations/{id}/messages/` | Send a message through REST; body: `{"body":"Hello"}` |
| POST | `/api/v1/conversations/{id}/mark-read/` | Mark incoming messages read |
| GET | `/api/v1/conversations/{id}/members/` | List active participants |
| POST | `/api/v1/conversations/{id}/add-members/` | Group owner/admin adds participants; body: `{"member_ids":[14]}` |
| POST | `/api/v1/conversations/{id}/remove-member/` | Group owner/admin removes participant; body: `{"user_id":14}` |

## WebSocket

Vite proxies this path to Django Channels:

```text
ws://localhost:5173/ws/chat/{conversation_id}/?token={JWT_ACCESS_TOKEN}
```

Client events:

```json
{"type":"message","body":"Hello there"}
{"type":"typing","is_typing":true}
{"type":"typing","is_typing":false}
{"type":"mark_read"}
```

Server events include `message.created`, `typing`, `presence`, `message.read`, and `error`.

## Security notes and current scope

- A WebSocket is accepted only for an authenticated user who is an active member of the conversation.
- REST conversation queries are scoped to conversations where the signed-in user is an active member.
- Message bodies are plain text and capped at 4,000 characters.
- The browser sends the JWT in the WebSocket query string for local development convenience. Query-string tokens can be recorded in proxy/access logs; production should use a short-lived WebSocket ticket or secure cookie-based authentication and ensure tokens are redacted from logs.
- Online presence is conversation-scoped and connection-based in this first implementation; production multi-device presence should use a Redis-backed connection registry.
- Message attachments, push notifications for offline users, message edit/delete controls, and complete group-member management UI are planned follow-up work. Group membership REST endpoints are included.
- The frontend was syntax-checked and backend files were Python-compiled during preparation. Full Django runtime tests and a frontend production build must still be run in the local project after dependencies are installed.

## Production ASGI server

Use an ASGI server for WebSockets. For example:

```bash
daphne -b 0.0.0.0 -p 8000 config.asgi:application
```

Do not serve the production backend solely through WSGI/Gunicorn if WebSocket chat is required.
