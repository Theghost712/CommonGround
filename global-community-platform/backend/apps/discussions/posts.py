"""Instagram-style photo posts: one request creates the post and all of its photos."""
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

import uuid

from django.core.files.base import ContentFile

from apps.common.media import MediaRejected, check_video, process_image, ranged_file_response
from apps.communities.models import Community, CommunityMembership
from apps.notifications.services import create_mention_notifications

from .images import build_variants, check_image_token
from .models import DiscussionAttachment
from .serializers import DiscussionSerializer

MAX_PHOTOS = 10
CAPTION_LIMIT = 2200
MAX_VIDEO_SECONDS = 180
MAX_POST_VIDEO_BYTES = 100 * 1024 * 1024
VIDEO_TYPES = {"mp4": "video/mp4", "mov": "video/quicktime", "webm": "video/webm"}


def reload_post(discussion, request):
    """Serialise a just-created post exactly like the feed does (counts, poll, media)."""
    from .polls import with_polls
    from .views import with_stats

    qs = with_polls(with_stats(type(discussion).objects.all(), request.user), request.user)
    discussion = qs.prefetch_related("attachments").select_related("author", "author__profile", "community").get(pk=discussion.pk)
    return DiscussionSerializer(discussion, context={"request": request}).data


def attach_photo(discussion, user, uploaded, alt_text=""):
    """Store the original plus optimised copies. Raises MediaRejected for bad files."""
    display, thumb, width, height, colour = build_variants(uploaded)
    attachment = DiscussionAttachment(
        discussion=discussion, uploaded_by=user, original_name=(uploaded.name or "photo")[:255],
        content_type="image/webp", size=display.size, width=width, height=height, color=colour, alt_text=alt_text[:300],
    )
    # The original upload is deliberately NOT stored: it can carry GPS location and
    # camera details. `file` points at the cleaned display copy instead.
    attachment.display.save(display.name, display, save=False)
    attachment.file.name = attachment.display.name
    attachment.thumbnail.save(thumb.name, thumb, save=False)
    attachment.save()
    return attachment


def notify_mentions(discussion, author):
    community = discussion.community
    create_mention_notifications(
        f"{discussion.title}\n{discussion.body}",
        author,
        target_url=f"/discussions/{discussion.id}",
        context_label=f"Mentioned you in a post: {(discussion.title or discussion.body)[:80]}",
        allowed_recipient_ids=(
            None if not community or community.visibility == Community.PUBLIC
            else community.memberships.filter(status=CommunityMembership.ACTIVE).values_list("user_id", flat=True)
        ),
    )


class PostCreateView(APIView):
    """POST /posts/ (multipart): images[] (1–10), alt_texts[], caption, category, community."""

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "uploads"

    def post(self, request):
        images = request.FILES.getlist("images")
        alt_texts = request.data.getlist("alt_texts") if hasattr(request.data, "getlist") else []
        caption = str(request.data.get("caption", "")).strip()
        if not images:
            raise ValidationError({"images": "Add at least one photo."})
        if len(images) > MAX_PHOTOS:
            raise ValidationError({"images": f"A post can have at most {MAX_PHOTOS} photos."})
        if len(caption) > CAPTION_LIMIT:
            raise ValidationError({"caption": f"Captions can be at most {CAPTION_LIMIT} characters."})

        serializer = DiscussionSerializer(
            data={"title": "", "body": caption, "content_html": "", "category": request.data.get("category") or "General", "community": request.data.get("community") or None},
            context={"request": request, "allow_untitled": True},
        )
        serializer.is_valid(raise_exception=True)
        saved = []
        try:
            with transaction.atomic():
                discussion = serializer.save(author=request.user)
                for index, uploaded in enumerate(images):
                    try:
                        saved.append(attach_photo(discussion, request.user, uploaded, alt_texts[index] if index < len(alt_texts) else ""))
                    except MediaRejected as error:
                        raise ValidationError({"images": f"Photo {index + 1}: {error}"})
        except ValidationError:
            for attachment in saved:  # the transaction rolled back the rows; remove the files too
                for field in (attachment.file, attachment.display, attachment.thumbnail):
                    field.delete(save=False)
            raise
        notify_mentions(discussion, request.user)
        return Response(reload_post(discussion, request), status=status.HTTP_201_CREATED)


class VideoPostCreateView(APIView):
    """POST /posts/video/ (multipart): video, poster (frame captured by the browser),
    duration_ms, caption, alt_text, category, community.

    There is no ffmpeg on the server, so the video is checked by signature and size
    and stored as uploaded; the browser supplies the poster frame and duration.
    """

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "uploads"

    def post(self, request):
        video = request.FILES.get("video")
        poster = request.FILES.get("poster")
        caption = str(request.data.get("caption", "")).strip()
        if not video:
            raise ValidationError({"video": "Choose a video."})
        if not poster:
            raise ValidationError({"poster": "A cover frame is required. Try another browser if this keeps happening."})
        if len(caption) > CAPTION_LIMIT:
            raise ValidationError({"caption": f"Captions can be at most {CAPTION_LIMIT} characters."})
        try:
            duration_ms = int(float(request.data.get("duration_ms", 0)))
        except (TypeError, ValueError):
            duration_ms = 0
        if duration_ms <= 0:
            raise ValidationError({"duration_ms": "We couldn't read the video's length."})
        if duration_ms > MAX_VIDEO_SECONDS * 1000:
            raise ValidationError({"video": f"Videos can be up to {MAX_VIDEO_SECONDS // 60} minutes long."})
        try:
            extension = check_video(video, MAX_POST_VIDEO_BYTES)
            display, thumb, (width, height) = process_image(poster, max_size=(1080, 1920), thumb_size=(480, 480))
        except MediaRejected as error:
            raise ValidationError({"video": str(error)})
        from .images import dominant_color

        serializer = DiscussionSerializer(
            data={"title": "", "body": caption, "content_html": "", "category": request.data.get("category") or "General", "community": request.data.get("community") or None},
            context={"request": request, "allow_untitled": True},
        )
        serializer.is_valid(raise_exception=True)
        attachment = None
        try:
            with transaction.atomic():
                discussion = serializer.save(author=request.user)
                attachment = DiscussionAttachment(
                    discussion=discussion, uploaded_by=request.user, original_name=(video.name or "video")[:255],
                    content_type=VIDEO_TYPES[extension], size=video.size, width=width, height=height,
                    color=dominant_color(thumb), alt_text=str(request.data.get("alt_text", ""))[:300], duration_ms=duration_ms,
                )
                attachment.file.save(f"{uuid.uuid4().hex}.{extension}", video, save=False)
                attachment.display.save(display.name, display, save=False)
                attachment.thumbnail.save(thumb.name, thumb, save=False)
                attachment.save()
        except Exception:
            if attachment is not None:
                for field in (attachment.file, attachment.display, attachment.thumbnail):
                    if field:
                        field.delete(save=False)
            raise
        notify_mentions(discussion, request.user)
        return Response(reload_post(discussion, request), status=status.HTTP_201_CREATED)


class DiscussionVideoView(APIView):
    """Stream a video post for a signed link, with HTTP Range (seeking, Safari)."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = []

    def get(self, request, pk):
        if check_image_token(pk, request.query_params.get("t", "")) != "video":
            raise PermissionDenied("This video link has expired. Reload the page.")
        attachment = get_object_or_404(DiscussionAttachment, pk=pk, content_type__startswith="video/")
        response = ranged_file_response(request, attachment.file, attachment.content_type, cache_seconds=6 * 60 * 60)
        if response.status_code != 302:  # a redirect to signed storage keeps its short cache
            response["Cache-Control"] = "private, max-age=21600"
        return response


class DiscussionImageView(APIView):
    """Serve an optimised post photo for a signed link (cacheable; no API token needed)."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = []

    def get(self, request, pk):
        kind = check_image_token(pk, request.query_params.get("t", ""))
        if kind is None:
            raise PermissionDenied("This image link has expired. Reload the page.")
        attachment = get_object_or_404(DiscussionAttachment, pk=pk)
        field = attachment.display if kind == "display" else attachment.thumbnail
        if not field:
            raise Http404
        response = ranged_file_response(request, field, "image/webp", cache_seconds=6 * 60 * 60)
        if response.status_code != 302:
            response["Cache-Control"] = "private, max-age=21600, immutable"
        return response
