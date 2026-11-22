# System Architecture

```text
Browser
  React + TypeScript + Vite
          |
          | HTTPS / JSON REST API
          v
Django + Django REST Framework
  |       |         |
  |       |         +-- Auth / JWT
  |       +------------ Communities / Memberships
  +-------------------- Discussions / Comments / Reactions
          |
          v
      PostgreSQL

Future real-time layer:
React WebSocket client <-> Django Channels <-> Redis
Future voice/video layer:
Django issues room access token -> LiveKit SFU -> participants
```

The browser never connects directly to PostgreSQL. All business rules and authorization checks are enforced by Django. The React client is an API consumer.
