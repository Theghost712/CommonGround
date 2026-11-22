# Software Requirements Specification — CommonGround MVP

## Purpose
CommonGround is a web platform for global communities and meaningful discussion. This MVP provides the authenticated community and discussion foundation.

## Actors
- Visitor: can view public communities and public/open discussions.
- Registered user: can create discussions, create communities, join public/restricted communities, react, comment, and reply.
- Community owner: can edit or delete their community.
- Community administrator: can edit their community.
- Platform administrator: can access Django Admin and platform records.

## Functional requirements
1. The system shall allow users to register and authenticate using JWT.
2. The system shall expose the authenticated user's basic profile.
3. Authenticated users shall be able to create communities.
4. The system shall support public, private, and restricted visibility values.
5. Users shall be able to join public/restricted communities.
6. Private community membership shall require an approval workflow (future implementation).
7. Users shall be able to create discussions, optionally associated with a community where they are members.
8. Visitors shall be able to read open discussions and public communities.
9. Authenticated users shall be able to react to discussions, comment, and reply.
10. Authors shall be able to edit/delete their own discussion and comment content.
11. Community owners shall control deletion; owners and administrators shall control community edits.

## Non-functional requirements
- Responsive web interface for desktop, tablet, and mobile browsers.
- API versioning under `/api/v1/`.
- Password validation and Django password hashing.
- Server-side permission enforcement and input validation.
- Pagination for collection endpoints.
- PostgreSQL support and SQLite local-development fallback.
- Maintainable modular Django apps and typed React components.

## Out of scope for this MVP
Real-time direct/group chat, voice/video, push notifications, polls, uploads, advanced discovery, paid membership, and full moderation workflows.
