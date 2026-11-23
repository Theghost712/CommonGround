"""Photos, videos, voice messages, view-once media and disappearing messages in chat.

- Photos are decoded and re-encoded (WebP, metadata stripped).
- Videos are stored, then re-encoded to H.264 MP4 in the background (apps/common/video.py).
- Voice messages are converted to AAC .m4a right away (small files; plays everywhere).
- View once: the payload never carries a link. A recipient asks for a two-minute link
  once (POST …/open/); after everyone has opened it, the file is deleted.
- Disappearing messages: a chat setting; each new message gets expires_at, and the
  scheduler deletes expired messages and their files.
"""

import os
import subprocess
import tempfile
import uuid
from datetime import timedelta

from django.core import signing
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.common.media import MediaRejected, check_video, process_image, ranged_file_response

from .models import Conversation, ConversationMember, Message, MessageOpen

LINK_SECONDS = 6 * 3600
ONCE_SECONDS = 120
MAX_VOICE_BYTES = 10 * 1024 * 1024
MAX_VOICE_MS = 5 * 60 * 1000
MAX_CHAT_VIDEO_BYTES = 50 * 1024 * 1024
DISAPPEAR_CHOICES = {0: "off", 3600: "1 hour", 86400: "24 hours", 7 * 86400: "7 days"}
VIEW_ONCE_KEEP = timedelta(minutes=5)  # let the last viewer finish loading before deleting
_signer = signing.TimestampSigner(salt="chat-media")

CONTENT_TYPES = {"webp": "image/webp", "jpg": "image/jpeg", "png": "image/png", "mp4": "video/mp4", "mov": "video/quicktime",
                 "webm": "video/webm", "m4a": "audio/mp4", "ogg": "audio/ogg", "mp3": "audio/mpeg"}


def media_url(message, which="media", once=False):
    field = message.media if which == "media" else message.thumbnail
    if not field:
        return ""
    token = _signer.sign(f"{message.pk}:{which}:{'once' if once else 'std'}")
    return f"{reverse('chat_media', args=[message.pk])}?t={token}"


def _check_token(message_id, token):
    for max_age in (ONCE_SECONDS, LINK_SECONDS):
        try:
            value = _signer.unsign(token, max_age=max_age)
        except signing.SignatureExpired:
            continue
        except signing.BadSignature:
            return None
        pk, which, mode = (value.split(":") + ["", "", ""])[:3]
        if pk != str(message_id):
            return None
        if mode == "once" and max_age != ONCE_SECONDS:
            return None  # view-once links only live two minutes
        return which, mode
    return None


# --------------------------------------------------------------- conversion
def convert_voice(source_bytes):
    """Any browser recording (WebM/Opus, Ogg, MP4/AAC) → AAC .m4a bytes + duration."""
    from apps.common.video import ffmpeg_exe, probe

    exe = ffmpeg_exe()
    if exe is None:
        raise MediaRejected("Voice messages aren't available on this server.")
    with tempfile.TemporaryDirectory(prefix="cg-voice-") as workdir:
        source, target = os.path.join(workdir, "in"), os.path.join(workdir, "voice.m4a")
        with open(source, "wb") as handle:
            handle.write(source_bytes)
        result = subprocess.run([exe, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-i", source, "-vn", "-map", "0:a:0",
                                 "-t", str(MAX_VOICE_MS // 1000), "-c:a", "aac", "-b:a", "64k", "-ac", "1", "-map_metadata", "-1",
                                 "-movflags", "+faststart", target], capture_output=True, timeout=90)
        if result.returncode != 0 or not os.path.exists(target):
            raise MediaRejected("That recording couldn't be read. Please try again.")
        _, _, duration_ms = probe(target)
        with open(target, "rb") as handle:
            return handle.read(), duration_ms


# --------------------------------------------------------------- creating
def deliver(message):
    """Read receipt for the sender, notify members, push the message live."""
    from apps.notifications.services import notify_chat_message

    from .models import MessageReadReceipt
    from .serializers import MessageSerializer
    from .services import broadcast_message, touch_conversation

    MessageReadReceipt.objects.get_or_create(message=message, user=message.sender)
    touch_conversation(message.conversation_id)
    message = Message.objects.select_related("sender", "conversation", "shared_post").get(pk=message.pk)
    notify_chat_message(message)
    data = MessageSerializer(message).data
    broadcast_message(data, message.conversation_id)
    return message, data


def expiry_for(conversation):
    seconds = conversation.disappear_seconds
    return timezone.now() + timedelta(seconds=seconds) if seconds else None


def _member_conversation(request, pk):
    conversation = Conversation.objects.filter(pk=pk, memberships__user=request.user, memberships__is_active=True).first()
    if conversation is None:
        raise PermissionDenied("You're not in this conversation.")
    from .services import direct_chat_blocked

    if direct_chat_blocked(conversation.pk, request.user):
        raise PermissionDenied("You can't message this account.")
    return conversation


class ChatMediaUploadView(APIView):
    """POST /conversations/<id>/media/ (multipart or JSON with file_key):
    kind photo|video|voice, file or file_key, caption, view_once, duration_ms, poster."""

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "uploads"

    def post(self, request, pk):
        from apps.common import video as video_processing
        from apps.common.uploads import claim_upload

        conversation = _member_conversation(request, pk)
        kind = str(request.data.get("kind", ""))
        if kind not in Message.MEDIA_KINDS:
            raise ValidationError({"kind": "Choose a photo, video or voice message."})
        caption = str(request.data.get("caption", "")).strip()[:1000]
        view_once = str(request.data.get("view_once", "")).lower() in ("1", "true", "yes", "on") and kind in (Message.PHOTO, Message.VIDEO)
        upload = request.FILES.get("file")
        claimed = None
        if upload is None and request.data.get("file_key"):
            claimed = claim_upload(request.user, request.data.get("file_key"), f"chat-{kind}")
        if upload is None and claimed is None:
            raise ValidationError({"file": "Choose a file."})

        message = Message(conversation=conversation, sender=request.user, kind=kind, body="" if view_once else caption,
                          view_once=view_once, expires_at=expiry_for(conversation))
        try:
            if kind == Message.PHOTO:
                source = claimed.download() if claimed else upload
                full, thumb, (width, height) = process_image(source, max_size=(1280, 1280), thumb_size=(480, 480))
                message.media.save(full.name, full, save=False)
                message.thumbnail.save(thumb.name, thumb, save=False)
                message.width, message.height = width, height
            elif kind == Message.VOICE:
                source = claimed.download() if claimed else upload
                if source.size > MAX_VOICE_BYTES:
                    raise MediaRejected("Voice messages can be at most 10 MB.")
                data, duration_ms = convert_voice(source.read())
                message.media.save(f"{uuid.uuid4().hex}.m4a", ContentFile(data), save=False)
                message.duration_ms = duration_ms
            else:
                if claimed is not None:
                    extension = check_video(claimed, claimed.size)
                    claimed.move_to(message.media, f"{uuid.uuid4().hex}.{extension}")
                else:
                    extension = check_video(upload, MAX_CHAT_VIDEO_BYTES)
                    message.media.save(f"{uuid.uuid4().hex}.{extension}", upload, save=False)
                try:
                    message.duration_ms = int(float(request.data.get("duration_ms") or 0)) or None
                except (TypeError, ValueError):
                    message.duration_ms = None
                poster = request.FILES.get("poster")
                if poster:
                    _, thumb, (width, height) = process_image(poster, max_size=(1080, 1920), thumb_size=(480, 480))
                    message.thumbnail.save(thumb.name, thumb, save=False)
                    message.width, message.height = width, height
                message.processing = video_processing.initial_status()
            with transaction.atomic():
                message.save()
                if kind == Message.VIDEO:
                    video_processing.schedule(message)
        except MediaRejected as error:
            message.delete_files()
            if claimed is not None:
                claimed.discard()
            raise ValidationError({"file": str(error)})
        if claimed is not None and kind != Message.VIDEO:
            claimed.discard()  # the processed copy is stored
        _, data = deliver(message)
        return Response(data, status=status.HTTP_201_CREATED)


class SharePostView(APIView):
    """POST /conversations/<id>/share-post/ {post_id, caption}: send a post into a chat."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    def post(self, request, pk):
        from apps.discussions.models import Discussion
        from apps.discussions.views import visible_discussions

        conversation = _member_conversation(request, pk)
        post = visible_discussions(request.user).filter(pk=request.data.get("post_id")).first()
        if post is None:
            raise ValidationError({"post_id": "That post isn't available."})
        message = Message.objects.create(conversation=conversation, sender=request.user, kind=Message.POST,
                                         body=str(request.data.get("caption", "")).strip()[:1000], shared_post=post,
                                         expires_at=expiry_for(conversation))
        Discussion.objects.filter(pk=post.pk).update(share_count=F("share_count") + 1)
        _, data = deliver(message)
        return Response(data, status=status.HTTP_201_CREATED)


class OpenViewOnceView(APIView):
    """POST /conversations/<id>/messages/<mid>/open/ → {url} valid for two minutes, once."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk, message_id):
        conversation = _member_conversation(request, pk)
        message = get_object_or_404(Message, pk=message_id, conversation=conversation, view_once=True, deleted_at__isnull=True)
        if message.sender_id == request.user.pk:
            raise PermissionDenied("View-once media can only be opened by the people you sent it to.")
        if not message.media:
            return Response({"detail": "This has already been opened."}, status=status.HTTP_410_GONE)
        _, created = MessageOpen.objects.get_or_create(message=message, user=request.user)
        if not created:
            return Response({"detail": "You've already opened this."}, status=status.HTTP_410_GONE)
        from .serializers import MessageSerializer
        from .services import broadcast_message

        broadcast_message(MessageSerializer(Message.objects.select_related("sender").get(pk=message.pk)).data, conversation.pk)
        return Response({"url": media_url(message, "media", once=True), "kind": message.kind, "seconds": ONCE_SECONDS})


class DeleteMessageView(APIView):
    """DELETE /conversations/<id>/messages/<mid>/: unsend your own message for everyone."""

    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk, message_id):
        conversation = Conversation.objects.filter(pk=pk, memberships__user=request.user, memberships__is_active=True).first()
        if conversation is None:
            raise PermissionDenied("You're not in this conversation.")
        message = get_object_or_404(Message, pk=message_id, conversation=conversation, deleted_at__isnull=True)
        if message.sender_id != request.user.pk:
            raise PermissionDenied("You can only unsend your own messages.")
        message.delete_files()
        Message.objects.filter(pk=message.pk).update(deleted_at=timezone.now(), body="", media="", thumbnail="", shared_post=None)
        from .services import broadcast_message

        broadcast_message({"id": message.pk, "conversation": conversation.pk, "is_deleted": True, "deleted": True}, conversation.pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DisappearingView(APIView):
    """POST /conversations/<id>/disappearing/ {seconds: 0|3600|86400|604800}."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        conversation = _member_conversation(request, pk)
        try:
            seconds = int(request.data.get("seconds", 0))
        except (TypeError, ValueError):
            seconds = -1
        if seconds not in DISAPPEAR_CHOICES:
            raise ValidationError({"seconds": "Choose off, 1 hour, 24 hours or 7 days."})
        if conversation.conversation_type == Conversation.GROUP:
            role = ConversationMember.objects.filter(conversation=conversation, user=request.user).values_list("role", flat=True).first()
            if role not in (ConversationMember.OWNER, ConversationMember.ADMIN):
                raise PermissionDenied("Only group admins can change this.")
        if conversation.disappear_seconds != seconds:
            Conversation.objects.filter(pk=conversation.pk).update(disappear_seconds=seconds)
            conversation.disappear_seconds = seconds
            name = request.user.get_full_name() or request.user.username
            text = (f"{name} turned off disappearing messages." if not seconds
                    else f"{name} turned on disappearing messages: new messages disappear after {DISAPPEAR_CHOICES[seconds]}.")
            notice = Message.objects.create(conversation=conversation, sender=request.user, kind=Message.SYSTEM, body=text)
            deliver(notice)
        return Response({"disappear_seconds": conversation.disappear_seconds})


class ChatMediaView(APIView):
    """GET /chat-media/<mid>/?t=&k=media|thumb — signed link, Range support."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = []

    def get(self, request, message_id):
        checked = _check_token(message_id, request.query_params.get("t", ""))
        if checked is None:
            raise PermissionDenied("This link has expired. Reload the chat.")
        which, mode = checked
        message = get_object_or_404(Message, pk=message_id, deleted_at__isnull=True)
        if message.expires_at and message.expires_at <= timezone.now():
            raise PermissionDenied("This message has disappeared.")
        if message.view_once and mode != "once":
            raise PermissionDenied("View-once media opens from the chat.")
        field = message.media if which == "media" else message.thumbnail
        if not field:
            raise PermissionDenied("This media is no longer available.")
        extension = field.name.rsplit(".", 1)[-1].lower()
        response = ranged_file_response(request, field, CONTENT_TYPES.get(extension, "application/octet-stream"), cache_seconds=300 if mode == "once" else 3600)
        if response.status_code != 302:
            response["Cache-Control"] = "private, no-store" if mode == "once" else "private, max-age=3600"
        return response


# --------------------------------------------------------------- clean-up job
def purge_chat_media():
    """Delete expired disappearing messages and the files of fully-opened view-once media."""
    now = timezone.now()
    removed = 0
    for message in Message.objects.filter(expires_at__lte=now)[:500]:
        message.delete_files()
        message.delete()
        removed += 1
    for message in Message.objects.filter(view_once=True, deleted_at__isnull=True).exclude(media="").select_related("conversation")[:500]:
        recipients = set(ConversationMember.objects.filter(conversation_id=message.conversation_id, is_active=True)
                         .exclude(user_id=message.sender_id).values_list("user_id", flat=True))
        opens = MessageOpen.objects.filter(message=message)
        opened = set(opens.values_list("user_id", flat=True))
        last = opens.order_by("-opened_at").values_list("opened_at", flat=True).first()
        if recipients and recipients <= opened and last and last <= now - VIEW_ONCE_KEEP:
            message.delete_files()
            Message.objects.filter(pk=message.pk).update(media="", thumbnail="")
            removed += 1
    return removed
