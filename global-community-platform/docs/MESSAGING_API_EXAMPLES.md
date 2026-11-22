# Messaging API examples

Authenticate with the existing access token in the normal REST authorization header:

```http
Authorization: Bearer <access-token>
```

## Start a private conversation

```http
POST /api/v1/conversations/start-direct/
Content-Type: application/json

{"user_id": 8}
```

## Create a group

```http
POST /api/v1/conversations/
Content-Type: application/json

{"title": "Community planning", "member_ids": [8, 11]}
```

## Send a REST message

```http
POST /api/v1/conversations/4/messages/
Content-Type: application/json

{"body": "Hello everyone"}
```

## WebSocket messages

Connect to:

```text
ws://localhost:5173/ws/chat/4/?token=<access-token>
```

Send:

```json
{"type": "message", "body": "Hello everyone"}
```

Typing state:

```json
{"type": "typing", "is_typing": true}
```

Mark all incoming messages as read:

```json
{"type": "mark_read"}
```

The server sends JSON events such as:

```json
{
  "type": "message.created",
  "message": {
    "id": 25,
    "conversation": 4,
    "sender": 3,
    "sender_username": "alex",
    "body": "Hello everyone",
    "read_count": 0
  }
}
```
