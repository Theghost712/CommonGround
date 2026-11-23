"""Server-side video conversion.

Every uploaded video (post or story) is re-encoded to H.264 + AAC in an MP4 with
"faststart", at most VIDEO_TRANSCODE_MAX_SIDE pixels on its long side and 30 fps.
That makes iPhone HEVC/.mov clips play on Android and desktop browsers, shrinks
big uploads, strips metadata (GPS location, device info) and replaces the user's
original bytes with a file the server wrote, so nothing hidden in the upload is
ever served. A file ffmpeg can't decode is not a playable video: it is deleted
and the post or story shows "This video couldn't be processed".

The original is served while conversion runs (status "pending"), so posting stays
instant. Work runs on one background thread per process; the scheduler
(apps/common/jobs.py) picks up anything left pending by a restart.
"""

import logging
import os
import re
import subprocess
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.apps import apps
from django.conf import settings
from django.core.files import File
from django.db import close_old_connections, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

PENDING, READY, FAILED = "pending", "", "failed"
STALE_CLAIM = timedelta(minutes=15)
MAX_ATTEMPTS = 3
MAX_SECONDS = 10 * 60

# model label -> (file field, extra fields updated on success)
TARGETS = {
    "discussions.DiscussionAttachment": "file",
    "stories.Story": "media",
}

_executor = None
_executor_lock = threading.Lock()


def ffmpeg_exe():
    try:
        import imageio_ffmpeg
    except ImportError:
        return None
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def enabled():
    return settings.VIDEO_TRANSCODE in ("thread", "sync") and ffmpeg_exe() is not None


def _pool():
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="video")
        return _executor


def initial_status():
    """Status for a freshly uploaded video."""
    return PENDING if enabled() else READY


def schedule(instance):
    """Convert `instance`'s video after the current transaction commits."""
    if not enabled() or getattr(instance, "processing", READY) != PENDING:
        return
    label = instance._meta.label

    def submit():
        if settings.VIDEO_TRANSCODE == "sync":
            process(label, instance.pk)
        else:
            _pool().submit(_process_in_thread, label, instance.pk)

    transaction.on_commit(submit)


def _process_in_thread(label, pk):
    try:
        process(label, pk)
    except Exception:
        logger.exception("Video conversion crashed for %s %s", label, pk)
    finally:
        close_old_connections()


def process_pending_videos():
    """Queue videos that are still pending (e.g. the process restarted mid-way)."""
    if not enabled():
        return 0
    cutoff = timezone.now() - STALE_CLAIM
    queued = 0
    for label in TARGETS:
        model = apps.get_model(label)
        stale = model.objects.filter(processing=PENDING, processing_attempts__lt=MAX_ATTEMPTS).exclude(
            processing_started_at__gt=cutoff).values_list("pk", flat=True)[:20]
        for pk in stale:
            if settings.VIDEO_TRANSCODE == "sync":
                process(label, pk)
            else:
                _pool().submit(_process_in_thread, label, pk)
            queued += 1
    return queued


def _claim(model, pk):
    """Atomically mark a pending video as being worked on (one worker wins)."""
    now = timezone.now()
    from django.db.models import F, Q

    return model.objects.filter(pk=pk, processing=PENDING, processing_attempts__lt=MAX_ATTEMPTS).filter(
        Q(processing_started_at__isnull=True) | Q(processing_started_at__lte=now - STALE_CLAIM)
    ).update(processing_started_at=now, processing_attempts=F("processing_attempts") + 1)


_DURATION = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_VIDEO_SIZE = re.compile(r"Stream #\S+.*Video:.*?(\d{2,5})x(\d{2,5})")


def probe(path):
    """(width, height, duration_ms) of a video, read from ffmpeg's banner."""
    result = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", path], capture_output=True, text=True, timeout=60)
    text = result.stderr
    size = _VIDEO_SIZE.search(text)
    duration = _DURATION.search(text)
    width, height = (int(size.group(1)), int(size.group(2))) if size else (None, None)
    duration_ms = None
    if duration:
        hours, minutes, seconds = duration.groups()
        duration_ms = int((int(hours) * 3600 + int(minutes) * 60 + float(seconds)) * 1000)
    return width, height, duration_ms


def transcode(source, target):
    """Re-encode `source` into `target` (MP4). Raises CalledProcessError/TimeoutExpired."""
    side = int(settings.VIDEO_TRANSCODE_MAX_SIDE)
    # Long side at most `side`, never upscaled, even dimensions (H.264 needs them).
    scale = (f"scale='if(gte(iw,ih),min({side},iw),-2)':'if(gte(iw,ih),-2,min({side},ih))',"
             "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p")
    command = [
        ffmpeg_exe(), "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
        "-i", source,
        "-map", "0:v:0", "-map", "0:a:0?",
        "-t", str(MAX_SECONDS),
        "-vf", scale, "-fpsmax", "30",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-maxrate", "3M", "-bufsize", "6M",
        "-profile:v", "high", "-level", "4.1",
        "-c:a", "aac", "-b:a", "128k", "-ac", "2",
        "-map_metadata", "-1", "-map_chapters", "-1", "-sn", "-dn",
        "-movflags", "+faststart", "-threads", "2",
        target,
    ]
    subprocess.run(command, check=True, capture_output=True, timeout=settings.VIDEO_TRANSCODE_TIMEOUT)


def process(label, pk):
    """Convert one video. Returns the final status, or None if someone else has it."""
    model = apps.get_model(label)
    field_name = TARGETS[label]
    if not _claim(model, pk):
        return None
    instance = model.objects.filter(pk=pk).first()
    if instance is None:
        return None
    field = getattr(instance, field_name)
    old_name = field.name
    with tempfile.TemporaryDirectory(prefix="cg-video-") as workdir:
        source = os.path.join(workdir, "source")
        target = os.path.join(workdir, "video.mp4")
        try:
            with field.storage.open(old_name, "rb") as remote, open(source, "wb") as local:
                for chunk in iter(lambda: remote.read(1024 * 1024), b""):
                    local.write(chunk)
        except Exception:
            # Storage hiccup: leave it pending; the scheduler retries (up to MAX_ATTEMPTS).
            logger.exception("Couldn't download %s %s for conversion", label, pk)
            _give_up_if_out_of_attempts(model, pk, field_name, old_name)
            return PENDING
        try:
            transcode(source, target)
            width, height, duration_ms = probe(target)
            if not width or not height:
                raise ValueError("no video stream in the output")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, OSError) as error:
            logger.warning("Video %s %s couldn't be converted: %s", label, pk, getattr(error, "stderr", error))
            _fail(model, pk, field_name, old_name)
            return FAILED

        directory = os.path.dirname(old_name)
        with open(target, "rb") as handle:
            converted = File(handle)
            converted.content_type = "video/mp4"  # object storage serves it with this type (Safari cares)
            new_name = field.storage.save(f"{directory}/{uuid.uuid4().hex}.mp4" if directory else f"{uuid.uuid4().hex}.mp4", converted)
        size = os.path.getsize(target)

    updates = {field_name: new_name, "processing": READY, "processing_started_at": None}
    if label == "discussions.DiscussionAttachment":
        updates.update(content_type="video/mp4", size=size, width=width, height=height)
        if duration_ms:
            updates["duration_ms"] = duration_ms
    elif duration_ms:
        updates["duration_ms"] = min(duration_ms, 60_000)
    # Only switch files if the row still exists and still points at the original.
    changed = model.objects.filter(pk=pk, **{field_name: old_name}).update(**updates)
    if changed:
        _delete_quietly(field.storage, old_name)
    else:
        _delete_quietly(field.storage, new_name)  # deleted or replaced meanwhile
    return READY


def _fail(model, pk, field_name, old_name):
    storage = model._meta.get_field(field_name).storage
    model.objects.filter(pk=pk).update(**{field_name: "", "processing": FAILED, "processing_started_at": None})
    _delete_quietly(storage, old_name)


def _give_up_if_out_of_attempts(model, pk, field_name, old_name):
    if model.objects.filter(pk=pk, processing_attempts__gte=MAX_ATTEMPTS).exists():
        _fail(model, pk, field_name, old_name)


def _delete_quietly(storage, name):
    if not name:
        return
    try:
        storage.delete(name)
    except Exception:
        logger.warning("Couldn't delete %s", name)
