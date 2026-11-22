# CommonGround — Community Management Update

This incremental update builds on the existing React + Django REST Framework project and its User Profile update.

## Included

- Public, restricted, and private community visibility.
- Community logo and cover image URLs.
- Community creator automatically becomes the owner.
- Membership statuses: active, pending, rejected.
- Public community join is immediate.
- Restricted community join creates a membership request.
- Private communities are visible only to active members; invitation endpoints are not included in this release.
- Owner/admin approval or rejection of membership requests.
- Owner/admin assignment of moderator roles; only the owner can assign administrators.
- Owner/admin removal of members; moderators can remove regular members.
- Community rules: create, edit, delete.
- Community announcements: publish, pin, edit, delete.
- Community member list and management dashboard in React.
- Access checks for discussions and comments in restricted/private communities.
- Django API tests for membership approval and access rules.

## Apply this patch

Extract the ZIP into the existing `global-community-platform` folder, preserving the folder paths and allowing the listed files to be overwritten.

Then run from the backend folder:

```bash
cd backend
source .venv/bin/activate
python manage.py makemigrations communities
python manage.py migrate
python manage.py check
python manage.py test apps.communities
```

Restart Django:

```bash
python manage.py runserver
```

In a second terminal, restart Vite:

```bash
cd frontend
npm run dev
```

## Using the module

1. Sign in and open **Communities**.
2. Create a community. The creator automatically becomes its owner.
3. Choose visibility:
   - **Public:** anyone can join immediately.
   - **Restricted:** people can find it and request to join; an owner or admin approves or rejects requests.
   - **Private:** visible to active members only. Private invitations are not yet implemented in this release.
4. Open a community. Use **Discussions**, **Members**, and **About & updates** tabs.
5. Owners and admins see **Manage**, including join requests and community settings.
6. Moderators can publish announcements and manage rules, and can remove regular members.
7. The owner can assign Admin or Moderator roles. Admins can assign Moderator roles.

## API endpoints

Base path: `/api/v1/communities/`

- `GET/POST /` — list visible communities / create a community.
- `GET/PATCH/DELETE /{id}/` — retrieve, update, or delete (owner only for delete).
- `POST /{id}/join/` — join a public community or request to join a restricted one.
- `POST /{id}/leave/` — leave or cancel a pending membership.
- `GET /{id}/members/` — list active members.
- `GET /{id}/membership-requests/` — owner/admin pending requests.
- `POST /{id}/approve-request/` — body: `{ "membership_id": 12 }`.
- `POST /{id}/reject-request/` — body: `{ "membership_id": 12 }`.
- `PATCH /{id}/update-member-role/` — body: `{ "membership_id": 12, "role": "moderator" }`.
- `POST /{id}/remove-member/` — body: `{ "membership_id": 12 }`.
- `GET/POST /{id}/rules/` — list or add a rule.
- `PATCH/DELETE /{id}/rules/{rule_id}/` — edit or delete a rule.
- `GET/POST /{id}/announcements/` — list or publish announcements.
- `PATCH/DELETE /{id}/announcements/{announcement_id}/` — edit or delete an announcement.

All management endpoints enforce permissions on the backend; hiding UI controls is not the security boundary.

## Migration note

The migration adds a `status` column with default `active`, so existing community memberships should remain active. Back up your SQLite or PostgreSQL database before applying migrations, especially if you have existing test data.
