"""Safe processing for user-uploaded media (stories now, posts later).

Images are decoded, rotated upright, shrunk, and re-encoded as WebP. Re-encoding drops
all metadata, so GPS location and camera details from phones never get published
(a common privacy leak). Videos are checked by their file signature, not just their
name, and size-limited; transcoding is left to a media pipeline in production.
"""
import warnings
from io import BytesIO

from django.core.files.base import ContentFile
from django.http import FileResponse, HttpResponse
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_IMAGE_PIXELS = 40_000_000  # ~ 8000×5000; rejects "decompression bomb" files
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "GIF", "MPO", "HEIF"}
MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_VIDEO_BYTES = 50 * 1024 * 1024
VIDEO_TYPES = {"video/mp4": "mp4", "video/quicktime": "mov", "video/webm": "webm"}


class MediaRejected(ValueError):
    """Raised with a user-facing message when an upload is not acceptable."""


def _encode(image, max_size, quality):
    copy = image.copy()
    copy.thumbnail(max_size, Image.Resampling.LANCZOS)
    buffer = BytesIO()
    copy.save(buffer, format="WEBP", quality=quality, method=4)
    return buffer.getvalue(), copy.size


def process_image(uploaded, max_size=(1080, 1920), thumb_size=(320, 568), quality=82):
    """Return (full ContentFile, thumbnail ContentFile, (width, height))."""
    if uploaded.size > MAX_IMAGE_BYTES:
        raise MediaRejected("Photos must be 15 MB or smaller.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(uploaded)
            if image.format not in IMAGE_FORMATS:
                raise MediaRejected("Upload a JPG, PNG, WEBP or GIF photo.")
            image.seek(0)  # first frame of animated GIF/WEBP
            image = ImageOps.exif_transpose(image)
            image.load()
    except MediaRejected:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning, OSError, SyntaxError):
        raise MediaRejected("That file is not a photo we can read.")
    has_alpha = image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)
    image = image.convert("RGBA" if has_alpha else "RGB")
    full, size = _encode(image, max_size, quality)
    thumb, _ = _encode(image, thumb_size, 70)
    return ContentFile(full, name="photo.webp"), ContentFile(thumb, name="thumb.webp"), size


def check_video(uploaded, max_bytes=MAX_VIDEO_BYTES):
    """Validate a video upload by signature and size; returns its file extension."""
    if uploaded.size > max_bytes:
        raise MediaRejected(f"Videos must be {max_bytes // (1024 * 1024)} MB or smaller.")
    head = uploaded.read(16)
    uploaded.seek(0)
    if head[4:8] == b"ftyp":
        return "mov" if head[8:10] == b"qt" else "mp4"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    raise MediaRejected("Upload an MP4, MOV or WebM video.")


def ranged_file_response(request, field, content_type, cache_seconds=3600):
    """Serve a stored file with HTTP Range support (needed for video seeking and Safari).

    In production, set MEDIA_ACCEL_REDIRECT_PREFIX so nginx streams the bytes instead
    of a Python worker (permission has already been checked by the caller).
    """
    from django.conf import settings

    prefix = getattr(settings, "MEDIA_ACCEL_REDIRECT_PREFIX", "")
    if prefix:
        response = HttpResponse(content_type=content_type)
        response["X-Accel-Redirect"] = prefix.rstrip("/") + "/" + field.name.lstrip("/")
        response["Cache-Control"] = f"private, max-age={cache_seconds}"
        response["X-Content-Type-Options"] = "nosniff"
        return response
    size = field.size
    range_header = request.headers.get("Range", "")
    if range_header.startswith("bytes="):
        start_text, _, end_text = range_header[6:].split(",")[0].partition("-")
        try:
            if start_text:
                start = int(start_text)
                end = min(int(end_text), size - 1) if end_text else size - 1
            else:  # suffix range: last N bytes
                start, end = max(0, size - int(end_text)), size - 1
        except ValueError:
            start, end = 0, size - 1
        if start >= size or start > end:
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{size}"
            return response
        handle = field.open("rb")
        handle.seek(start)
        response = HttpResponse(handle.read(end - start + 1), status=206, content_type=content_type)
        handle.close()
        response["Content-Range"] = f"bytes {start}-{end}/{size}"
        response["Content-Length"] = str(end - start + 1)
    else:
        response = FileResponse(field.open("rb"), content_type=content_type)
        response["Content-Length"] = str(size)
    response["Accept-Ranges"] = "bytes"
    response["Cache-Control"] = f"private, max-age={cache_seconds}"
    response["X-Content-Type-Options"] = "nosniff"
    return response
