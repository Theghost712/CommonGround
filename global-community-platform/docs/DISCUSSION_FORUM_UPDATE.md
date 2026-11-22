# Discussion Forum Enhancement

This update expands the core CommonGround discussion experience.

## Included features

- Rich-text discussion composer (bold, italic, underline, headings, lists, quotes and links).
- Server-side HTML sanitization with Bleach and client-side sanitization with DOMPurify.
- Discussion categories and category counts.
- Search by title, body, category, author and community.
- Trending discussions ranked by comments, reactions and bookmarks over the recent 30-day window. If there is no recent activity, the endpoint ranks the available discussions.
- Four reaction types: like, insightful, support and celebrate. Each member has one active reaction per discussion; clicking the same reaction again removes it.
- Discussion bookmarks and a saved-discussions page.
- Nested comment replies (API response includes up to three nested reply levels).
- Image/document attachments: JPG, PNG, GIF, WEBP, PDF, DOC, DOCX and TXT; maximum 10 MB per file and 5 files per composer.
- Private/restricted attachment downloads checked against active community membership.
- Responsive feed, search/filter controls, rich composer, discussion detail and saved-discussions view.

## Apply the update

Extract the update ZIP into the existing `global-community-platform` project root. It updates the discussion app, backend configuration, React discussion pages, app navigation and package dependencies. Keep the existing `db.sqlite3` or PostgreSQL database; do not delete it.

### Backend

```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt
python manage.py makemigrations discussions
python manage.py migrate
python manage.py check
python manage.py test apps.discussions
python manage.py runserver
```

### Frontend (second terminal)

```bash
cd frontend
npm install
npm run dev
```

If Vite was already running, stop it with `Ctrl+C` before restarting it.

## API endpoints

- `GET /api/v1/discussions/` — latest discussions; accepts `?search=`, `?category=`, `?community=`.
- `GET /api/v1/discussions/categories/` — categories and discussion counts.
- `GET /api/v1/discussions/trending/` — engagement-ranked discussions.
- `GET /api/v1/discussions/bookmarked/` — current user's saved discussions (JWT required).
- `POST /api/v1/discussions/{id}/react/` — toggle/update reaction; body: `{"reaction_type":"like"}`; other values: `insightful`, `support`, `celebrate`.
- `POST /api/v1/discussions/{id}/bookmark/` — toggle bookmark.
- `GET/POST /api/v1/discussions/{id}/comments/` — list top-level comments/create a comment; include `parent` to reply to a comment in the same discussion.
- `GET/POST /api/v1/discussions/{id}/attachments/` — list or upload a multipart file using field name `file`.
- `GET /api/v1/attachments/{id}/download/` — download/preview an attachment; private and restricted community files require active membership.

## Storage and production note

Files are stored under `backend/media/` in local development but are not exposed through a public `/media/` route. Downloads pass through an API endpoint that checks membership for private and restricted communities. Before production, move files to private object storage, add malware/content scanning, configure backups, and retain authorization checks. The current extension/MIME/size validation is a baseline, not a substitute for malware scanning.

## Notes

- Run `makemigrations discussions` in the existing backend virtual environment so Django creates a migration that matches the current local database history. Do not delete your database.
- The rich-text source is sanitized on the backend before being stored. The frontend also sanitizes content before rendering.
- The local API test suite is included in `backend/apps/discussions/tests.py`. Run it after applying migrations.
