# CommonGround Profile Module Update

This update adds an editable authenticated user profile to the existing React + Django REST Framework project.

## Backend

- Adds `UserProfile` with bio, country, preferred language, interests, avatar URL, and website.
- Adds `GET/PATCH /api/v1/auth/profile/` for the signed-in user.
- Creates a profile during registration and lazily creates one for accounts that existed before this update.
- Adds profile administration in Django Admin.

## Frontend

- Adds a responsive `/profile` page.
- Adds **My profile** to the sidebar.
- Allows editing first name, last name, bio, country, preferred language, interests, avatar URL, and website.
- Uses the existing REST API client and JWT authentication.

Avatar image upload is not included yet; `avatar_url` accepts a publicly accessible image URL. File uploads and storage will be a separate feature.

## Apply the update

Extract the update ZIP into the existing `global-community-platform` project root, allowing it to overwrite the listed files. Then run:

```bash
cd backend
source .venv/bin/activate
python manage.py makemigrations accounts
python manage.py migrate
python manage.py check
```

Restart Django after migration. In a separate terminal, restart Vite:

```bash
cd frontend
npm run dev
```

After signing in, open **My profile** from the left navigation or visit `http://localhost:5173/profile`.

## API

- `GET /api/v1/auth/profile/` — get the signed-in user's profile.
- `PATCH /api/v1/auth/profile/` — update profile fields.

Both endpoints require a valid JWT access token.
