"""For You ranking, reposts, view tracking and sponsored posts.

For You (like a short-video app's main feed) scores every recent visible post for
the viewer:

    score = (engagement + affinity + 1) / (age_hours + 2) ^ 1.3   × 0.25 if already seen

- engagement: reactions×3 + comments×4 + bookmarks×5 + shares×6 + views×0.05
- affinity: +40 if you follow the author, +25 if you liked or commented on their
  posts in the last 30 days, +15 per hashtag you engaged with recently (max 3)
- seen: posts you already viewed sink (watched to the end: ×0.1)

Everything is computed in SQL with subqueries, so one page is one query no matter
how many posts, likes or views exist.

Sponsored posts: an admin sets sponsored_until (and a sponsor name) on a post in
the admin. Feeds insert one active sponsored post per page (rotating), it is
labelled "Sponsored", and impressions and "Learn more" clicks are counted.
"""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Case, Count, Exists, ExpressionWrapper, F, FloatField, OuterRef, Subquery, Value, When
from django.db.models.expressions import RawSQL
from django.db.models.functions import Cast, Coalesce, Greatest, Least, Power
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from .models import Comment, Discussion, DiscussionAttachment, DiscussionReaction, PostView

CANDIDATE_DAYS = 45
SPONSORED_EVERY = 8


class ForYouPagination(PageNumberPagination):
    page_size = 12
    max_page_size = 30
    page_size_query_param = "page_size"


def rank_for_you(queryset, user):
    """Annotate `fy_score` on a with_stats() queryset and order by it."""
    since = timezone.now() - timedelta(days=30)
    authenticated = user is not None and user.is_authenticated
    engagement = (Cast(F("reactions_total"), FloatField()) * 3 + Cast(F("comments_total"), FloatField()) * 4
                  + Cast(F("bookmarks_total"), FloatField()) * 5 + Cast(F("share_count"), FloatField()) * 6
                  + Cast(F("view_count"), FloatField()) * 0.05)
    affinity = Value(0.0)
    seen_factor = Value(1.0)
    if authenticated:
        from apps.social.models import Follow

        follows = Exists(Follow.objects.filter(follower=user, following=OuterRef("author")))
        liked_author = Exists(DiscussionReaction.objects.filter(user=user, discussion__author=OuterRef("author"), created_at__gte=since))
        commented_author = Exists(Comment.objects.filter(author=user, discussion__author=OuterRef("author"), created_at__gte=since))
        liked_tags = DiscussionReaction.objects.filter(user=user, created_at__gte=since).values("discussion__hashtags")
        tag_matches = (Discussion.hashtags.through.objects.filter(discussion=OuterRef("pk"), hashtag__in=liked_tags)
                       .order_by().values("discussion").annotate(n=Count("pk")).values("n")[:1])
        affinity = (Case(When(follows, then=Value(40.0)), default=Value(0.0), output_field=FloatField())
                    + Case(When(liked_author | commented_author, then=Value(25.0)), default=Value(0.0), output_field=FloatField())
                    + Cast(Least(Coalesce(Subquery(tag_matches), Value(0)), Value(3)), FloatField()) * 15)
        view = PostView.objects.filter(user=user, discussion=OuterRef("pk"))
        seen_factor = Case(
            When(Exists(view.filter(completed=True)), then=Value(0.1)),
            When(Exists(view), then=Value(0.25)),
            default=Value(1.0), output_field=FloatField(),
        )
    age_hours = _age_hours()
    score = ExpressionWrapper((engagement + affinity + Value(1.0)) * seen_factor / Power(age_hours + Value(2.0), Value(1.3)), output_field=FloatField())
    return queryset.annotate(fy_score=score).order_by("-fy_score", "-created_at", "-id")


def _age_hours():
    """Hours since the post was created, in SQL (PostgreSQL or SQLite)."""
    from django.db import connection

    if connection.vendor == "postgresql":
        sql = "(EXTRACT(EPOCH FROM (NOW() - discussions_discussion.created_at)) / 3600.0)"
    else:
        sql = "((julianday('now') - julianday(discussions_discussion.created_at)) * 24.0)"
    return RawSQL(sql, [], output_field=FloatField())


def active_sponsored(queryset):
    return queryset.filter(sponsored_until__gt=timezone.now())


def inject_sponsored(request, results, base_queryset, page_number=1):
    """Insert one sponsored post (serialized) into a page of serialized posts."""
    if not results:
        return results
    candidates = list(active_sponsored(base_queryset).order_by("pk")[:20])
    if not candidates:
        return results
    # A sponsored post shows once per page, in its sponsored slot, never as a duplicate.
    sponsored_ids = {c.pk for c in candidates}
    results = [item for item in results if item["id"] not in sponsored_ids]
    sponsored = candidates[(max(page_number, 1) - 1) % len(candidates)]
    Discussion.objects.filter(pk=sponsored.pk).update(sponsored_impressions=F("sponsored_impressions") + 1)
    from .serializers import DiscussionSerializer

    data = DiscussionSerializer(sponsored, context={"request": request}).data
    position = min(3, len(results))
    return results[:position] + [data] + results[position:]


class ForYouView(APIView):
    """GET /api/v1/feed/for-you/?media=videos&page=N — personalised ranking."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from .polls import with_polls
        from .serializers import DiscussionSerializer
        from .views import visible_discussions, with_stats

        base = visible_discussions(request.user)
        from apps.safety.services import muted_post_authors

        muted = muted_post_authors(request.user)
        if muted:
            base = base.exclude(author_id__in=muted)
        qs = base.filter(created_at__gte=timezone.now() - timedelta(days=CANDIDATE_DAYS)).exclude(sponsored_until__gt=timezone.now())
        media = request.query_params.get("media")
        if media in ("videos", "photos"):
            prefix = "video/" if media == "videos" else "image/"
            qs = qs.filter(Exists(DiscussionAttachment.objects.filter(discussion=OuterRef("pk"), content_type__startswith=prefix)))
        if not qs.exists():
            qs = base.exclude(sponsored_until__gt=timezone.now())
            if media in ("videos", "photos"):
                prefix = "video/" if media == "videos" else "image/"
                qs = qs.filter(Exists(DiscussionAttachment.objects.filter(discussion=OuterRef("pk"), content_type__startswith=prefix)))
        qs = with_polls(with_stats(qs, request.user), request.user).select_related(
            "author", "author__profile", "community", "repost_of__author", "repost_of__author__profile").prefetch_related("attachments", "repost_of__attachments")
        ranked = rank_for_you(qs, request.user)
        paginator = ForYouPagination()
        page = paginator.paginate_queryset(ranked, request, view=self)
        results = DiscussionSerializer(page, many=True, context={"request": request}).data
        page_number = paginator.page.number if paginator.page else 1
        sponsored_base = base
        if media in ("videos", "photos"):
            prefix = "video/" if media == "videos" else "image/"
            sponsored_base = base.filter(Exists(DiscussionAttachment.objects.filter(discussion=OuterRef("pk"), content_type__startswith=prefix)))
        results = inject_sponsored(request, list(results), sponsored_base, page_number)
        return paginator.get_paginated_response(results)


class RecordViewsView(APIView):
    """POST /api/v1/feed/views/ {views: [{id, ms, completed}]} — batched from the feed."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    def post(self, request):
        items = request.data.get("views")
        if not isinstance(items, list):
            raise ValidationError({"views": "Send a list of views."})
        recorded = 0
        for item in items[:50]:
            try:
                post_id = int(item.get("id"))
                watched = max(0, min(int(item.get("ms") or 0), 10 * 60 * 1000))
            except (TypeError, ValueError, AttributeError):
                continue
            completed = bool(item.get("completed"))
            if not Discussion.objects.filter(pk=post_id).exists():
                continue
            try:
                with transaction.atomic():
                    PostView.objects.create(user=request.user, discussion_id=post_id, watched_ms=watched, completed=completed)
                Discussion.objects.filter(pk=post_id).update(view_count=F("view_count") + 1)
            except IntegrityError:
                PostView.objects.filter(user=request.user, discussion_id=post_id).update(
                    watched_ms=Greatest(F("watched_ms"), Value(watched)), completed=Value(True) if completed else F("completed"),
                    viewed_at=timezone.now())
            recorded += 1
        return Response({"recorded": recorded})


class RepostView(APIView):
    """POST /api/v1/discussions/<id>/repost/ {comment?}: share a post to your followers.
    DELETE removes your plain repost of it."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    def post(self, request, pk):
        from apps.notifications.models import Notification
        from apps.notifications.services import create_notification

        from .serializers import DiscussionSerializer
        from .views import visible_discussions

        post = get_object_or_404(visible_discussions(request.user), pk=pk)
        original = post.repost_of or post
        if original.community_id and original.community.visibility != "public":
            raise ValidationError({"detail": "Posts from private communities can't be reposted."})
        comment = str(request.data.get("comment", "")).strip()[:2000]
        if not comment and Discussion.objects.filter(author=request.user, repost_of=original, body="").exists():
            raise ValidationError({"detail": "You already reposted this."})
        repost = Discussion.objects.create(author=request.user, repost_of=original, body=comment, title="", category=original.category)
        Discussion.objects.filter(pk=original.pk).update(share_count=F("share_count") + 1)
        if original.author_id != request.user.pk:
            name = request.user.get_full_name() or request.user.username
            create_notification(recipient=original.author, notification_type=Notification.SYSTEM, title=f"{name} reposted your post",
                                body=comment[:140], target_url=f"/discussions/{repost.pk}", actor=request.user,
                                data={"discussion_id": repost.pk, "original_id": original.pk})
        return Response(DiscussionSerializer(repost, context={"request": request}).data, status=status.HTTP_201_CREATED)

    def delete(self, request, pk):
        original = get_object_or_404(Discussion, pk=pk)
        original = original.repost_of or original
        deleted, _ = Discussion.objects.filter(author=request.user, repost_of=original, body="").delete()
        if deleted:
            Discussion.objects.filter(pk=original.pk, share_count__gt=0).update(share_count=F("share_count") - 1)
        return Response({"removed": bool(deleted)})


class SponsoredClickView(APIView):
    """POST /api/v1/discussions/<id>/sponsored-click/ → {url}; counts the click."""

    permission_classes = [permissions.AllowAny]

    def post(self, request, pk):
        post = get_object_or_404(Discussion, pk=pk, sponsored_until__gt=timezone.now())
        Discussion.objects.filter(pk=post.pk).update(sponsored_clicks=F("sponsored_clicks") + 1)
        return Response({"url": post.sponsor_url or f"/discussions/{post.pk}"})


def prune_post_views():
    """Keep 90 days of view history (enough for ranking)."""
    PostView.objects.filter(viewed_at__lt=timezone.now() - timedelta(days=90)).delete()
