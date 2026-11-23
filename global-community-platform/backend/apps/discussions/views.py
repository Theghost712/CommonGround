from datetime import timedelta
from pathlib import Path

from django.db.models import Count, Exists, F, IntegerField, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import CursorPagination
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.communities.models import Community, CommunityMembership
from apps.communities.access import approved_community_content_q
from .models import Comment, Discussion, DiscussionAttachment, DiscussionBookmark, DiscussionReaction
from .serializers import CommentSerializer, DiscussionAttachmentSerializer, DiscussionSerializer
from apps.notifications.services import notify_discussion_comment, notify_discussion_reaction, create_mention_notifications

MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024
MAX_ATTACHMENTS_PER_DISCUSSION = 5
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf", ".doc", ".docx", ".txt"}
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "application/pdf", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "text/plain", "application/octet-stream"}
DISCUSSION_CATEGORIES = ["General", "Technology", "Education", "Business", "Entrepreneurship", "Politics", "Governance", "Health", "Environment", "Sports", "Culture", "Entertainment", "Science", "Community Development"]


class FeedCursorPagination(CursorPagination):
    """Constant-cost paging for endless feeds: no COUNT(*) and no OFFSET scans."""

    page_size = 20
    ordering = ("-created_at", "-id")


def _related_count(model):
    """COUNT of related rows as an indexed correlated subquery (no joins, no row explosion)."""
    counts = model.objects.filter(discussion=OuterRef("pk")).order_by().values("discussion").annotate(n=Count("pk")).values("n")[:1]
    return Coalesce(Subquery(counts, output_field=IntegerField()), Value(0))


def with_stats(qs, user):
    """Annotate counts and the viewer's own reaction/bookmark without loading those rows.

    Loading every like/comment/bookmark to count them made the feed 16× slower on
    popular posts and trending 13 s; subqueries keep cost independent of popularity.
    """
    from .models import DiscussionBookmark, DiscussionReaction

    qs = qs.annotate(
        comments_total=_related_count(Comment),
        reactions_total=_related_count(DiscussionReaction),
        bookmarks_total=_related_count(DiscussionBookmark),
    )
    if user is not None and user.is_authenticated:
        mine = DiscussionReaction.objects.filter(discussion=OuterRef("pk"), user=user).values("reaction_type")[:1]
        qs = qs.annotate(
            my_reaction_type=Subquery(mine),
            my_bookmark=Exists(DiscussionBookmark.objects.filter(discussion=OuterRef("pk"), user=user)),
        )
    return qs


def visible_discussions(user):
    """Discussions `user` may see.

    Open posts and public communities, plus communities they belong to; never posts by
    someone in a block with them; and open posts by private accounts only for followers.
    """
    visible = Q(community__isnull=True) | Q(community__visibility=Community.PUBLIC)
    authenticated = user is not None and user.is_authenticated
    if authenticated:
        # EXISTS instead of a join: no duplicate rows, so no expensive DISTINCT.
        visible |= Q(Exists(CommunityMembership.objects.filter(community=OuterRef("community"), user=user, status=CommunityMembership.ACTIVE)))
    qs = Discussion.objects.filter(approved_community_content_q("community"), visible)
    private_open_post = Q(community__isnull=True, author__profile__is_private=True)
    if authenticated:
        from apps.safety.services import blocked_user_ids
        from apps.social.models import Follow

        blocked = blocked_user_ids(user)
        if blocked:
            qs = qs.exclude(author_id__in=blocked)
        followed = Follow.objects.filter(follower=user).values("following_id")
        qs = qs.exclude(private_open_post & ~Q(author=user) & ~Q(author_id__in=followed))
    else:
        qs = qs.exclude(private_open_post)
    return qs


class DiscussionViewSet(viewsets.ModelViewSet):
    serializer_class = DiscussionSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title", "body", "content_html", "category", "author__username", "community__name"]
    ordering_fields = ["created_at", "title"]
    ordering = ["-created_at"]

    def get_queryset(self):
        from .polls import with_polls

        qs = with_polls(with_stats(visible_discussions(self.request.user), self.request.user), self.request.user).select_related("author", "author__profile", "community").prefetch_related("attachments")
        if self.request.query_params.get("feed") == "following":
            # Posts from people the user follows, plus their own (like Instagram's Following feed).
            if not self.request.user.is_authenticated:
                return qs.none()
            from apps.social.models import Follow

            followed = Follow.objects.filter(follower=self.request.user).values("following_id")
            qs = qs.filter(Q(author_id__in=followed) | Q(author=self.request.user))
        tag = self.request.query_params.get("tag", "").strip().lstrip("#").lower()
        if tag:
            qs = qs.filter(hashtags__name=tag)
        media = self.request.query_params.get("media")
        if media in ("photos", "videos"):
            prefix = "image/" if media == "photos" else "video/"
            qs = qs.filter(Exists(DiscussionAttachment.objects.filter(discussion=OuterRef("pk"), content_type__startswith=prefix)))
        elif media == "polls":
            qs = qs.filter(poll__isnull=False)
        author = self.request.query_params.get("author")
        if author:
            qs = qs.filter(author__username=author)
        elif self.action in ("list", "trending"):
            # Muted people stay out of feeds (their profile still shows their posts).
            from apps.safety.services import muted_post_authors

            muted = muted_post_authors(self.request.user)
            if muted:
                qs = qs.exclude(author_id__in=muted)
        community_id = self.request.query_params.get("community")
        if community_id:
            qs = qs.filter(community_id=community_id)
        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category__iexact=category)
        return qs

    @property
    def paginator(self):
        # ?paginate=cursor (used by the home feeds) switches to cursor paging; older
        # screens keep page numbers and totals.
        if not hasattr(self, "_paginator"):
            use_cursor = self.action == "list" and self.request.query_params.get("paginate") == "cursor"
            self._paginator = FeedCursorPagination() if use_cursor else self.pagination_class()
        return self._paginator

    def perform_create(self, serializer):
        discussion = serializer.save(author=self.request.user)
        create_mention_notifications(
            f"{discussion.title}\n{discussion.body}\n{discussion.content_html}",
            self.request.user,
            target_url=f"/discussions/{discussion.id}",
            context_label=f"Mentioned you in the discussion: {discussion.title}",
            allowed_recipient_ids=(
                None if not discussion.community or discussion.community.visibility == Community.PUBLIC
                else discussion.community.memberships.filter(status=CommunityMembership.ACTIVE).values_list("user_id", flat=True)
            ),
        )

    def perform_update(self, serializer):
        if self.get_object().author_id != self.request.user.id and not self.request.user.is_staff:
            raise PermissionDenied("You can only edit your own discussion.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.author_id != self.request.user.id and not self.request.user.is_staff:
            raise PermissionDenied("You can only delete your own discussion.")
        instance.delete()

    @action(detail=False, methods=["get"], permission_classes=[permissions.AllowAny])
    def categories(self, request):
        rows = self.get_queryset().values("category").annotate(count=Count("id")).order_by("category")
        counts = {row["category"]: row["count"] for row in rows}
        names = list(dict.fromkeys(DISCUSSION_CATEGORIES + list(counts.keys())))
        return Response([{"name": name, "count": counts.get(name, 0)} for name in names])

    @action(detail=False, methods=["get"], permission_classes=[permissions.AllowAny])
    def trending(self, request):
        recent = self.get_queryset().filter(created_at__gte=timezone.now() - timedelta(days=30))
        if not recent.exists():
            recent = self.get_queryset()
        recent = self.filter_queryset(recent)
        ranked = recent.annotate(
            engagement_score=F("comments_total") * 2 + F("reactions_total") * 3 + F("bookmarks_total") * 4
        ).order_by("-engagement_score", "-created_at")
        page = self.paginate_queryset(ranked)
        serializer = self.get_serializer(page if page is not None else ranked, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)

    @action(detail=False, methods=["get"], permission_classes=[permissions.IsAuthenticated])
    def bookmarked(self, request):
        saved = self.get_queryset().filter(Exists(DiscussionBookmark.objects.filter(discussion=OuterRef("pk"), user=request.user)))
        page = self.paginate_queryset(saved)
        serializer = self.get_serializer(page if page is not None else saved, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def react(self, request, pk=None):
        discussion = self.get_object()
        reaction_type = request.data.get("reaction_type", "like")
        allowed = {choice[0] for choice in DiscussionReaction.REACTION_CHOICES}
        if reaction_type not in allowed:
            raise ValidationError({"reaction_type": f"Choose one of: {', '.join(sorted(allowed))}."})
        reaction = DiscussionReaction.objects.filter(discussion=discussion, user=request.user).first()
        if reaction and reaction.reaction_type == reaction_type:
            reaction.delete()
            reacted, current = False, None
        elif reaction:
            reaction.reaction_type = reaction_type
            reaction.save(update_fields=["reaction_type"])
            reacted, current = True, reaction_type
        else:
            DiscussionReaction.objects.create(discussion=discussion, user=request.user, reaction_type=reaction_type)
            reacted, current = True, reaction_type
        if reacted:
            notify_discussion_reaction(discussion, request.user, reaction_type)
        return Response({"reacted": reacted, "reaction_type": current, "reactions_count": discussion.reactions.count()})

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def bookmark(self, request, pk=None):
        discussion = self.get_object()
        bookmark, created = DiscussionBookmark.objects.get_or_create(discussion=discussion, user=request.user)
        if not created:
            bookmark.delete()
        return Response({"bookmarked": created, "bookmarks_count": discussion.bookmarks.count()})

    @action(detail=True, methods=["get", "post"], permission_classes=[permissions.IsAuthenticatedOrReadOnly])
    def comments(self, request, pk=None):
        discussion = self.get_object()
        if request.method == "GET":
            from apps.safety.services import blocked_user_ids

            blocked = blocked_user_ids(request.user)
            comments = discussion.comments.filter(parent__isnull=True).exclude(author_id__in=blocked).select_related("author").prefetch_related("replies__author")
            return Response(CommentSerializer(comments, many=True, context={"request": request, "blocked_ids": blocked}).data)
        serializer = CommentSerializer(data={**request.data, "discussion": discussion.id}, context={"request": request})
        serializer.is_valid(raise_exception=True)
        comment = serializer.save(author=request.user)
        notify_discussion_comment(comment)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get", "post"], permission_classes=[permissions.IsAuthenticatedOrReadOnly], parser_classes=[MultiPartParser, FormParser])
    def attachments(self, request, pk=None):
        discussion = self.get_object()
        if request.method == "GET":
            files = discussion.attachments.all()
            return Response(DiscussionAttachmentSerializer(files, many=True, context={"request": request}).data)
        if not request.user.is_authenticated:
            return Response({"detail": "Authentication is required."}, status=status.HTTP_401_UNAUTHORIZED)
        if discussion.author_id != request.user.id and not request.user.is_staff:
            # Attachments render as part of the author's post, so only the author may add them.
            raise PermissionDenied("Only the author of this discussion can add attachments.")
        if discussion.community and discussion.community.visibility != Community.PUBLIC:
            member = CommunityMembership.objects.filter(community=discussion.community, user=request.user, status=CommunityMembership.ACTIVE).exists()
            if not member:
                raise PermissionDenied("You must be an active community member to upload an attachment.")
        if discussion.attachments.count() >= MAX_ATTACHMENTS_PER_DISCUSSION:
            raise ValidationError({"file": f"A discussion can have at most {MAX_ATTACHMENTS_PER_DISCUSSION} attachments."})
        uploaded = request.FILES.get("file")
        if not uploaded:
            raise ValidationError({"file": "Choose a file to upload."})
        # Any image is decoded and re-encoded (whatever content type the browser claimed),
        # so the stored file is one the server wrote.
        if Path(uploaded.name).suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
            from apps.common.media import MediaRejected

            from .posts import attach_photo

            try:
                attachment = attach_photo(discussion, request.user, uploaded, str(request.data.get("alt_text", "")))
            except MediaRejected as error:
                raise ValidationError({"file": str(error)})
            return Response(DiscussionAttachmentSerializer(attachment, context={"request": request}).data, status=status.HTTP_201_CREATED)
        extension = Path(uploaded.name).suffix.lower()
        content_type = uploaded.content_type or "application/octet-stream"
        if extension not in ALLOWED_EXTENSIONS or content_type not in ALLOWED_CONTENT_TYPES:
            raise ValidationError({"file": "Allowed files: JPG, PNG, GIF, WEBP, PDF, DOC, DOCX, and TXT."})
        if uploaded.size > MAX_ATTACHMENT_SIZE:
            raise ValidationError({"file": "File size must not exceed 10 MB."})
        from apps.common.scanning import UnsafeFile, scan_document

        try:
            data = uploaded.read()
            uploaded.seek(0)
            scan_document(data, extension)
        except UnsafeFile as error:
            raise ValidationError({"file": str(error)})
        attachment = DiscussionAttachment.objects.create(discussion=discussion, uploaded_by=request.user, file=uploaded, original_name=Path(uploaded.name.replace("\\", "/")).name[:255], content_type=content_type, size=uploaded.size)
        return Response(DiscussionAttachmentSerializer(attachment, context={"request": request}).data, status=status.HTTP_201_CREATED)


class CommentViewSet(viewsets.ModelViewSet):
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        qs = Comment.objects.select_related("author", "discussion", "parent")
        discussion_id = self.request.query_params.get("discussion")
        if discussion_id:
            qs = qs.filter(discussion_id=discussion_id)
        from apps.safety.services import blocked_user_ids

        # Same rules as posts (communities, blocks, private accounts) plus blocked commenters.
        return qs.filter(discussion__in=visible_discussions(self.request.user)).exclude(author_id__in=blocked_user_ids(self.request.user))

    def perform_create(self, serializer):
        comment = serializer.save(author=self.request.user)
        notify_discussion_comment(comment)

    def perform_update(self, serializer):
        if self.get_object().author_id != self.request.user.id:
            raise PermissionDenied("You can only edit your own comment.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.author_id != self.request.user.id and not self.request.user.is_staff:
            raise PermissionDenied("You can only delete your own comment.")
        instance.delete()


class DiscussionAttachmentDownloadView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, pk):
        attachment = get_object_or_404(
            DiscussionAttachment.objects.select_related("discussion__community").filter(
                approved_community_content_q("discussion__community")
            ),
            pk=pk,
        )
        community = attachment.discussion.community
        if community and community.visibility != Community.PUBLIC:
            allowed = bool(
                request.user.is_authenticated
                and CommunityMembership.objects.filter(
                    community=community,
                    user=request.user,
                    status=CommunityMembership.ACTIVE,
                ).exists()
            )
            if not allowed:
                raise PermissionDenied("You must be an active community member to access this attachment.")
        # Photos are served from the cleaned copy so GPS/camera metadata in older
        # original uploads is never handed out.
        source = attachment.display if attachment.display else attachment.file
        response = FileResponse(
            source.open("rb"),
            as_attachment=not attachment.is_image,
            filename=attachment.original_name,
            content_type="image/webp" if attachment.display else (attachment.content_type or "application/octet-stream"),
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        response["Vary"] = "Authorization"
        return response


class TrendingHashtagsView(APIView):
    """GET /tags/trending/ — most used tags in visible posts over the last 7 days."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from .models import Hashtag

        since = timezone.now() - timedelta(days=7)
        visible = visible_discussions(request.user).filter(created_at__gte=since)
        rows = (
            Hashtag.objects.filter(discussions__in=visible)
            .annotate(posts=Count("discussions", distinct=True))
            .order_by("-posts", "name")[:15]
        )
        return Response([{"name": tag.name, "posts": tag.posts} for tag in rows])


class HashtagDetailView(APIView):
    """GET /tags/<name>/ — how many visible posts use a tag."""

    permission_classes = [permissions.AllowAny]

    def get(self, request, name):
        tag = name.strip().lstrip("#").lower()
        count = visible_discussions(request.user).filter(hashtags__name=tag).count()
        return Response({"name": tag, "posts": count})
