"""Direct uploads: the browser sends big files straight to object storage.

Hosts like Vercel cap request bodies (4.5 MB), so videos can't pass through the
app. Instead: (1) the app hands out a one-time upload URL for a private
"incoming/<user>/…" key, (2) the browser PUTs the file there, (3) the create
endpoint receives the key, checks that this user uploaded it, its size and its real
type, and moves or processes it into place.
"""
import uuid

from django.conf import settings
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from rest_framework import permissions, serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

MB = 1024 * 1024
TYPES = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif", "image/heic": ".heic",
    "video/mp4": ".mp4", "video/quicktime": ".mov", "video/webm": ".webm",
    "audio/webm": ".weba", "audio/ogg": ".ogg", "audio/mp4": ".m4a", "audio/mpeg": ".mp3", "audio/aac": ".aac", "audio/x-m4a": ".m4a",
}
PURPOSES = {"post-photo": "image/", "post-video": "video/", "story-photo": "image/", "story-video": "video/",
            "chat-photo": "image/", "chat-video": "video/", "chat-voice": "audio/"}


def direct_uploads_available():
    return hasattr(default_storage, "create_upload_url")


def max_bytes(purpose):
    if purpose.endswith("photo"):
        return 15 * MB
    if purpose == "chat-voice":
        return 10 * MB
    if purpose == "story-video":
        return min(50 * MB, settings.DIRECT_UPLOAD_MAX_VIDEO_MB * MB)
    return settings.DIRECT_UPLOAD_MAX_VIDEO_MB * MB


def _record_key(key):
    return f"direct-upload:{key}"


class UploadRequestSerializer(serializers.Serializer):
    purpose = serializers.ChoiceField(choices=list(PURPOSES))
    content_type = serializers.CharField(max_length=100)
    size = serializers.IntegerField(min_value=1)

    def validate(self, attrs):
        content_type = attrs["content_type"].split(";")[0].strip().lower()
        if content_type not in TYPES or not content_type.startswith(PURPOSES[attrs["purpose"]]):
            raise serializers.ValidationError({"content_type": "This file type isn't supported here."})
        limit = max_bytes(attrs["purpose"])
        if attrs["size"] > limit:
            raise serializers.ValidationError({"size": f"Files can be at most {limit // MB} MB."})
        attrs["content_type"] = content_type
        return attrs


class UploadConfigView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response({
            "direct": direct_uploads_available(),
            "max_photo_mb": max_bytes("post-photo") // MB,
            "max_video_mb": max_bytes("post-video") // MB,
            "max_story_video_mb": max_bytes("story-video") // MB,
        })


class UploadRequestView(APIView):
    """POST {purpose, content_type, size} → {key, upload_url, headers}."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "uploads"

    def post(self, request):
        if not direct_uploads_available():
            return Response({"detail": "Direct uploads aren't available on this server."}, status=status.HTTP_400_BAD_REQUEST)
        data = UploadRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        key = f"incoming/{request.user.pk}/{uuid.uuid4().hex}{TYPES[values['content_type']]}"
        upload_url = default_storage.create_upload_url(key)
        cache.set(_record_key(key), {"user": request.user.pk, "purpose": values["purpose"]}, timeout=2 * 3600)
        return Response({
            "key": key, "upload_url": upload_url, "method": "PUT",
            "headers": {"Content-Type": values["content_type"], "x-upsert": "false"},
        }, status=status.HTTP_201_CREATED)


class ClaimedUpload:
    """A file the user put in storage, checked and ready to process or move."""

    def __init__(self, key, size):
        self.key = key
        self.size = size
        self.name = key.rsplit("/", 1)[-1]
        self._head = None
        self._position = 0

    # Enough of a file API for check_video(): it reads the first bytes, then seeks back.
    def read(self, length=-1):
        if self._head is None:
            self._head = default_storage.read_head(self.key, 64)
        data = self._head[self._position:] if length < 0 else self._head[self._position:self._position + length]
        self._position += len(data)
        return data

    def seek(self, position, whence=0):
        self._position = position

    def download(self):
        """The whole file (photos: they are re-encoded anyway)."""
        with default_storage.open(self.key) as handle:
            content = ContentFile(handle.read(), name=self.name)
        content.size = len(content)
        return content

    def move_to(self, field, filename):
        """Move into place under the field's upload_to path, without re-uploading."""
        final = field.field.generate_filename(field.instance, filename)
        default_storage.move(self.key, final)
        field.name = final
        cache.delete(_record_key(self.key))
        return final

    def discard(self):
        try:
            default_storage.delete(self.key)
        finally:
            cache.delete(_record_key(self.key))


def claim_upload(user, key, purpose):
    """Check that `user` uploaded `key` for `purpose`; return a ClaimedUpload."""
    key = str(key or "")
    record = cache.get(_record_key(key))
    if not key.startswith(f"incoming/{user.pk}/") or not record or record["user"] != user.pk or record["purpose"] != purpose:
        raise ValidationError({"file": "That upload has expired or isn't yours. Please upload it again."})
    try:
        size = default_storage.size(key)
    except FileNotFoundError:
        raise ValidationError({"file": "The upload didn't finish. Please try again."})
    if size > max_bytes(purpose):
        default_storage.delete(key)
        raise ValidationError({"file": f"Files can be at most {max_bytes(purpose) // MB} MB."})
    return ClaimedUpload(key, size)
