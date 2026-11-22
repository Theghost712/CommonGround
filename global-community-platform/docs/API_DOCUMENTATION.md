# API Documentation

Base URL: `http://127.0.0.1:8000/api/v1/`

Authentication: `Authorization: Bearer <access_token>` for protected operations.

## Register
`POST /auth/register/`

```json
{
  "username": "alex",
  "email": "alex@example.com",
  "first_name": "Alex",
  "last_name": "M",
  "password": "Use-A-Strong-Password-123!",
  "password_confirm": "Use-A-Strong-Password-123!"
}
```

## Obtain token
`POST /auth/token/`

```json
{ "username": "alex", "password": "Use-A-Strong-Password-123!" }
```

## Create community
`POST /communities/`

```json
{
  "name": "Curious Minds",
  "description": "A space to exchange ideas and learn together.",
  "category": "Education",
  "visibility": "public"
}
```

## Create discussion
`POST /discussions/`

```json
{
  "title": "How can communities support lifelong learning?",
  "body": "I would love to hear examples and ideas...",
  "category": "Education",
  "community": 1
}
```

Use `community: null` for an open discussion not associated with a community.

## Create comment or reply
`POST /discussions/{id}/comments/`

```json
{ "body": "One idea is to create local learning circles.", "parent": null }
```

Set `parent` to a comment ID to reply to that comment.
