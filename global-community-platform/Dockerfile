# CommonGround: one image serving the React app, the API and WebSockets.
# Build: docker build -t commonground global-community-platform

FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FRONTEND_DIST=/app/frontend/dist \
    STATIC_ROOT=/app/backend/staticfiles
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt
COPY backend/ ./
COPY deploy/ /app/deploy/
COPY --from=frontend /app/frontend/dist /app/frontend/dist
RUN DJANGO_SECRET_KEY=build-only-not-secret python manage.py collectstatic --noinput \
 && useradd --create-home --uid 10001 app && chown -R app /app
USER app
EXPOSE 8000
CMD ["/app/deploy/container-start.sh"]
