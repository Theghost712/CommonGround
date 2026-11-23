"""Optimised images for discussion/photo posts.

Each uploaded photo gets a 1080px WebP display copy, a 480px grid thumbnail, its
dimensions (so pages reserve space and don't jump) and a dominant colour shown while
loading. Links are signed so <img> tags can load them without the API token and the
browser can cache them; permission is checked when the link is handed out.
"""
import hashlib
from django.core import signing
from django.urls import reverse
from PIL import Image

from apps.common.media import process_image

IMAGE_LINK_SECONDS = 6 * 60 * 60
_signer = signing.TimestampSigner(salt="commonground.post-image")


def dominant_color(content_file):
    """Average colour of the thumbnail as #rrggbb (a cheap, pleasant placeholder)."""
    content_file.seek(0)
    with Image.open(content_file) as image:
        pixel = image.convert("RGB").resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
    content_file.seek(0)
    return "#{:02x}{:02x}{:02x}".format(*pixel)


def build_variants(uploaded):
    """Return (display ContentFile, thumb ContentFile, width, height, colour)."""
    # One decode produces both copies. The thumbnail keeps its aspect ratio within
    # 480×480 (the grid crops it square with CSS); tall posters keep full height at 1080 wide.
    display, thumb, size = process_image(uploaded, max_size=(1080, 2700), thumb_size=(480, 480), quality=82)
    return display, thumb, size[0], size[1], dominant_color(thumb)


def image_url(attachment, kind):
    """Signed URL for the 'display' or 'thumb' variant (falls back to nothing)."""
    field = attachment.display if kind == "display" else attachment.thumbnail
    if not field:
        return ""
    token = _signer.sign(f"{attachment.pk}:{kind}")
    return f"{reverse('discussion_image', args=[attachment.pk])}?t={token}"


def video_url(attachment):
    """Signed, Range-capable URL for a video post's video file."""
    if not attachment.file or not (attachment.content_type or "").startswith("video/"):
        return ""
    token = _signer.sign(f"{attachment.pk}:video")
    # The version changes when the server swaps in the converted file, so browsers
    # don't mix cached ranges of the original with the new one.
    version = hashlib.sha1(attachment.file.name.encode()).hexdigest()[:10]
    return f"{reverse('discussion_video', args=[attachment.pk])}?t={token}&v={version}"


def check_image_token(attachment_id, token):
    try:
        value = _signer.unsign(token, max_age=IMAGE_LINK_SECONDS)
    except signing.BadSignature:
        return None
    pk, _, kind = value.partition(":")
    if pk != str(attachment_id) or kind not in {"display", "thumb", "video"}:
        return None
    return kind
