"""Periodic jobs that run inside the web process.

Hosts like Vercel have no crontab, so each web process runs a small scheduler
thread, and GET/POST /api/v1/internal/tick/ runs due jobs too (for an external
pinger or Vercel Cron). Every job is idempotent, and `cache.add` (an atomic
"set if absent" in the shared database/Redis cache) makes sure only one process
runs a job per interval, however many instances are awake.
"""

import logging
import threading
import time

from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.db import close_old_connections

logger = logging.getLogger(__name__)


def _command(name, *args):
    def run():
        import io

        call_command(name, *args, verbosity=0, stdout=io.StringIO())  # keep logs quiet
    return run


def _process_videos():
    from apps.common.video import process_pending_videos

    process_pending_videos()


def _expire_calls():
    from apps.calls.group import expire_stale_group_calls
    from apps.calls.services import expire_stale_calls

    expire_stale_calls()
    expire_stale_group_calls()


def _purge_chat():
    from apps.messaging.media import purge_chat_media

    purge_chat_media()


# (name, interval in seconds, function)
JOBS = [
    ("purge_chat", 120, _purge_chat),
    ("weekly_digest", 86400, lambda: __import__("apps.notifications.digest", fromlist=["send_weekly_digests"]).send_weekly_digests()),
    ("measure_storage", 86400, lambda: __import__("apps.common.usage", fromlist=["measure_storage"]).measure_storage()),
    ("prune_post_views", 86400, lambda: __import__("apps.discussions.feed", fromlist=["prune_post_views"]).prune_post_views()),
    ("expire_calls", 60, _expire_calls),
    ("process_videos", 120, _process_videos),
    ("event_reminders", 300, _command("send_event_reminders")),
    ("purge_stories", 3600, _command("purge_expired_stories")),
    ("flush_tokens", 86400, _command("flushexpiredtokens")),
    ("clear_sessions", 86400, _command("clearsessions")),
]


def run_due_jobs(names=None):
    """Run every job whose interval has passed; returns the names that ran."""
    ran = []
    for name, interval, function in JOBS:
        if names is not None and name not in names:
            continue
        # The key expires after the interval, so the next caller after that runs it.
        if not cache.add(f"job-lock:{name}", time.time(), timeout=interval):
            continue
        try:
            function()
            ran.append(name)
        except Exception:  # one broken job must not stop the others
            logger.exception("Scheduled job %s failed", name)
    return ran


_started = False
_start_lock = threading.Lock()


def start_scheduler():
    """Start the background loop once per process (when SCHEDULER_ENABLED)."""
    global _started
    if not getattr(settings, "SCHEDULER_ENABLED", False):
        return
    with _start_lock:
        if _started:
            return
        _started = True

    def loop():
        time.sleep(15)  # let the server finish starting
        while True:
            try:
                run_due_jobs()
            except Exception:
                logger.exception("Scheduler loop error")
            finally:
                close_old_connections()
            time.sleep(30)

    threading.Thread(target=loop, name="commonground-scheduler", daemon=True).start()


def tick_view(request):
    """GET/POST /api/v1/internal/tick/: run whatever jobs are due.

    Safe to leave public: jobs are idempotent and each runs at most once per
    interval. When CRON_SECRET is set (Vercel Cron sends it), a matching
    `Authorization: Bearer` header is required.
    """
    import hmac

    from django.http import JsonResponse

    secret = getattr(settings, "CRON_SECRET", "")
    if secret:
        given = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(given.encode(), secret.encode()):
            return JsonResponse({"detail": "Not allowed."}, status=403)
    if request.method not in ("GET", "POST"):
        return JsonResponse({"detail": "Use GET or POST."}, status=405)
    return JsonResponse({"ran": run_due_jobs()}, headers={"Cache-Control": "no-store"})
