from collections import OrderedDict

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import F
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.common import video as video_processing
from apps.common.media import MediaRejected, check_video, process_image, ranged_file_response
from apps.messaging.services import get_or_create_direct_conversation, send_message
from apps.social.serializers import PersonSerializer
from apps.social.services import people_queryset, relationship_map

from .access import can_view, check_media_token, visible_stories
from .models import CloseFriend, Story, StoryHiddenFrom, StoryView
from .serializers import StoryCreateSerializer, StorySerializer

User = get_user_model()
TRAY_STORY_LIMIT = 500


def _serialize(request, stories, seen_ids=None):
    return StorySerializer(stories, many=True, context={"request": request, "seen_ids": seen_ids or set()}).data


class StoryTrayView(APIView):
    """GET /stories/tray/ — people with active stories, own first, then unseen, then seen."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        me = request.user
        from apps.safety.services import muted_story_authors

        stories = list(visible_stories(me).exclude(author_id__in=muted_story_authors(me)).select_related("author").order_by("author_id", "created_at")[:TRAY_STORY_LIMIT])
        seen_ids = set(StoryView.objects.filter(viewer=me, story_id__in=[s.pk for s in stories]).values_list("story_id", flat=True))
        grouped = OrderedDict()
        for story in stories:
            grouped.setdefault(story.author_id, []).append(story)
        people = {u.pk: u for u in people_queryset().filter(pk__in=grouped.keys())}
        relations = relationship_map(me, grouped.keys())
        entries = []
        for author_id, items in grouped.items():
            if author_id not in people:
                continue
            all_seen = author_id == me.pk or all(s.pk in seen_ids for s in items)
            entries.append({
                "user": PersonSerializer(people[author_id], context={"relations": relations}).data,
                "stories": _serialize(request, items, seen_ids),
                "all_seen": all_seen,
                "latest_at": items[-1].created_at,
                "_own": author_id == me.pk,
            })
        entries.sort(key=lambda e: (not e["_own"], e["all_seen"], -e["latest_at"].timestamp()))
        for entry in entries:
            entry.pop("_own")
        return Response(entries)


class StoryCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "uploads"

    def post(self, request):
        serializer = StoryCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        story = Story(
            author=request.user, media_type=data["media_type"], text=data["text"].strip(),
            background=data["background"], alt_text=data["alt_text"].strip(), audience=data["audience"],
        )
        claimed = None
        if data.get("file_key") and not data.get("file") and story.media_type in (Story.IMAGE, Story.VIDEO):
            from apps.common.uploads import claim_upload

            purpose = "story-photo" if story.media_type == Story.IMAGE else "story-video"
            claimed = claim_upload(request.user, data["file_key"], purpose)
            data["file"] = claimed.download() if story.media_type == Story.IMAGE else claimed
        try:
            if story.media_type == Story.IMAGE:
                full, thumb, _ = process_image(data["file"])
                story.media.save(full.name, full, save=False)
                story.thumbnail.save(thumb.name, thumb, save=False)
                story.duration_ms = 5000
            elif story.media_type == Story.VIDEO:
                if claimed is not None:
                    extension = check_video(claimed, claimed.size)
                    claimed.move_to(story.media, f"clip.{extension}")
                else:
                    extension = check_video(data["file"])
                    data["file"].name = f"clip.{extension}"
                    story.media.save(data["file"].name, data["file"], save=False)
                story.duration_ms = data["duration_ms"]
                story.processing = video_processing.initial_status()
                if data.get("thumbnail"):
                    _, thumb, _ = process_image(data["thumbnail"])  # poster frame captured by the browser
                    story.thumbnail.save(thumb.name, thumb, save=False)
            else:
                story.duration_ms = min(15000, max(5000, len(story.text) * 60))
            story.save()
            video_processing.schedule(story)
        except MediaRejected as error:
            story.delete_files()
            if claimed is not None:
                claimed.discard()
            raise ValidationError({"file": str(error)})
        if claimed is not None and story.media_type == Story.IMAGE:
            claimed.discard()  # the processed copy is stored; drop the original
        return Response(_serialize(request, [story])[0], status=status.HTTP_201_CREATED)


class StoryDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _story(self, request, pk):
        story = get_object_or_404(Story.objects.select_related("author"), pk=pk)
        if not can_view(request.user, story):
            raise Http404
        return story

    def get(self, request, pk):
        story = self._story(request, pk)
        seen = set(StoryView.objects.filter(viewer=request.user, story=story).values_list("story_id", flat=True))
        return Response(_serialize(request, [story], seen)[0])

    def delete(self, request, pk):
        story = get_object_or_404(Story, pk=pk, author=request.user)
        story.delete_files()
        story.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class StoryMediaView(APIView):
    """Serves story media for a valid signed link (no JWT, so <img>/<video> can use it)."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = []

    def get(self, request, pk):
        kind = check_media_token(pk, request.query_params.get("t", ""))
        if kind is None:
            raise PermissionDenied("This link has expired. Reload the story.")
        story = get_object_or_404(Story, pk=pk)
        if not story.is_active:
            raise Http404
        field = story.media if kind == "media" else story.thumbnail
        if not field:
            raise Http404
        if kind == "thumb" or story.media_type == Story.IMAGE:
            content_type = "image/webp"
        else:
            content_type = {"mp4": "video/mp4", "mov": "video/quicktime", "webm": "video/webm"}.get(field.name.rsplit(".", 1)[-1], "video/mp4")
        return ranged_file_response(request, field, content_type)


class StoryViewedView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        story = get_object_or_404(Story, pk=pk)
        if not can_view(request.user, story):
            raise Http404
        if story.author_id != request.user.pk:
            try:
                with transaction.atomic():
                    _, created = StoryView.objects.get_or_create(story=story, viewer=request.user)
                    if created:
                        Story.objects.filter(pk=story.pk).update(view_count=F("view_count") + 1)
            except IntegrityError:
                pass  # two tabs marked it at once; already counted
        return Response({"seen": True})


class StoryViewersView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        story = get_object_or_404(Story, pk=pk, author=request.user)
        views = list(story.views.select_related("viewer").order_by("-viewed_at")[:500])
        people = {u.pk: u for u in people_queryset().filter(pk__in=[v.viewer_id for v in views])}
        relations = relationship_map(request.user, people.keys())
        return Response({
            "count": story.view_count,
            "viewers": [
                {"viewed_at": v.viewed_at, "person": PersonSerializer(people[v.viewer_id], context={"relations": relations}).data}
                for v in views if v.viewer_id in people
            ],
        })


class StoryReplyView(APIView):
    """Reply privately to a story; arrives as a direct message, like Instagram."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        story = get_object_or_404(Story.objects.select_related("author"), pk=pk)
        if not can_view(request.user, story):
            raise Http404
        if story.author_id == request.user.pk:
            raise ValidationError({"body": "You can't reply to your own story."})
        body = str(request.data.get("body", "")).strip()
        if not body:
            raise ValidationError({"body": "Write a reply."})
        if len(body) > 1000:
            raise ValidationError({"body": "Replies can be at most 1000 characters."})
        label = "photo" if story.media_type == Story.IMAGE else "video" if story.media_type == Story.VIDEO else "story"
        from apps.safety.services import is_blocked_between

        if is_blocked_between(request.user, story.author):
            raise Http404
        conversation = get_or_create_direct_conversation(request.user, story.author)
        message = send_message(conversation, request.user, f"↩ Replied to your {label}: {body}")
        return Response({"conversation_id": conversation.pk, "message_id": message.pk}, status=status.HTTP_201_CREATED)


class StoryUserView(APIView):
    """GET /stories/user/<username>/ — a person's active stories you may watch (for their profile ring)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, username):
        author = get_object_or_404(User, username=username, is_active=True)
        stories = list(visible_stories(request.user).filter(author=author).order_by("created_at"))
        seen_ids = set(StoryView.objects.filter(viewer=request.user, story__in=stories).values_list("story_id", flat=True))
        return Response(_serialize(request, stories, seen_ids))


class _AudienceListView(APIView):
    """Manage a per-user list (close friends / hidden from) of other members."""

    permission_classes = [permissions.IsAuthenticated]
    model = None
    owner_field = "owner"
    member_field = None

    def get(self, request):
        ids = self.model.objects.filter(owner=request.user).values_list(f"{self.member_field}_id", flat=True)
        users = list(people_queryset().filter(pk__in=list(ids)).order_by("username"))
        relations = relationship_map(request.user, [u.pk for u in users])
        return Response(PersonSerializer(users, many=True, context={"relations": relations}).data)

    def put(self, request, username):
        member = get_object_or_404(User, username=username, is_active=True)
        if member.pk == request.user.pk:
            raise ValidationError({"detail": "You can't add yourself."})
        self.model.objects.get_or_create(owner=request.user, **{self.member_field: member})
        return Response({"username": member.username, "added": True})

    def delete(self, request, username):
        member = get_object_or_404(User, username=username)
        self.model.objects.filter(owner=request.user, **{self.member_field: member}).delete()
        return Response({"username": member.username, "added": False})


class CloseFriendsView(_AudienceListView):
    model = CloseFriend
    member_field = "friend"


class HiddenFromView(_AudienceListView):
    model = StoryHiddenFrom
    member_field = "hidden_user"
