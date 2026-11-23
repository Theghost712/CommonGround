"""How much of the free hosting limits CommonGround uses (shown in the admin).

- Database size: sum of this app's tables (PostgreSQL) or the SQLite file.
- Media storage: walks the storage bucket once a day (scheduler job) and caches
  the total. The same walk deletes abandoned direct uploads ("incoming/…" files
  older than a day, from uploads that were never posted), which only waste space.
"""

import logging
import os
from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.core.cache import cache
from django.db import connection

logger = logging.getLogger(__name__)
CACHE_KEY = "usage:storage"
MB = 1024 * 1024


def database_bytes():
    try:
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COALESCE(SUM(pg_total_relation_size(c.oid)), 0) FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind = 'r' AND n.nspname = current_schema()"
                )
                return int(cursor.fetchone()[0])
        name = settings.DATABASES["default"].get("NAME")
        return os.path.getsize(name) if name and os.path.exists(str(name)) else 0
    except Exception:
        logger.exception("Couldn't measure the database size")
        return None


def measure_storage(clean_incoming=True):
    """Total bytes in media storage; also removes abandoned uploads. Cached for 2 days."""
    from django.core.files.storage import default_storage

    total, files, removed = 0, 0, 0
    cutoff = datetime.now(dt_timezone.utc) - timedelta(days=1)
    if hasattr(default_storage, "walk"):
        for name, size, updated in default_storage.walk(""):
            if clean_incoming and name.startswith("incoming/") and updated:
                try:
                    stamp = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                except ValueError:
                    stamp = None
                if stamp and stamp < cutoff:
                    try:
                        default_storage.delete(name)
                        removed += 1
                        continue
                    except Exception:
                        logger.warning("Couldn't delete abandoned upload %s", name)
            total += size
            files += 1
    else:
        root = str(settings.MEDIA_ROOT)
        for folder, _, names in os.walk(root):
            for name in names:
                try:
                    total += os.path.getsize(os.path.join(folder, name))
                    files += 1
                except OSError:
                    pass
    result = {"bytes": total, "files": files, "removed_abandoned": removed, "measured_at": datetime.now(dt_timezone.utc).isoformat()}
    cache.set(CACHE_KEY, result, timeout=2 * 86400)
    return result


def usage_summary():
    """Numbers for the admin dashboard (never walks storage itself; uses the daily result)."""
    from django.contrib.auth import get_user_model

    db = database_bytes()
    storage = cache.get(CACHE_KEY)
    db_limit = int(getattr(settings, "FREE_DATABASE_MB", 500)) * MB
    storage_limit = int(getattr(settings, "FREE_STORAGE_MB", 1024)) * MB

    def item(label, used, limit, hint):
        pct = round(used * 100 / limit) if used is not None and limit else None
        return {"label": label, "used": used, "limit": limit, "pct": pct, "hint": hint,
                "level": "danger" if pct is not None and pct >= 90 else "warn" if pct is not None and pct >= 70 else "ok"}

    return [
        item("Database", db, db_limit, "Posts, messages, members (Supabase free: 500 MB)"),
        item("Media storage", storage["bytes"] if storage else None, storage_limit,
             "Photos, videos, voice notes (Supabase free: 1 GB)" + (f" · measured {storage['measured_at'][:10]}" if storage else " · measured daily")),
        {"label": "Members", "used": get_user_model().objects.filter(is_active=True).count(), "limit": None, "pct": None,
         "hint": "Active accounts", "level": "ok"},
    ]
