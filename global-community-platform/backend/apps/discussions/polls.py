"""Polls on posts: create a poll post, vote, change or take back a vote.

Results stay hidden until you vote (so early numbers don't sway people), except
for the author and once the poll has closed.
"""
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from .models import Discussion, Poll, PollOption, PollVote

MIN_OPTIONS, MAX_OPTIONS = 2, 6
MIN_HOURS, MAX_HOURS = 1, 7 * 24


def with_polls(qs, user):
    """Load polls for a page of posts in a fixed number of queries."""
    qs = qs.select_related("poll").prefetch_related(
        Prefetch("poll__options", queryset=PollOption.objects.annotate(vote_count=Count("votes"))),
    )
    if user is not None and user.is_authenticated:
        qs = qs.prefetch_related(Prefetch("poll__votes", queryset=PollVote.objects.filter(user=user), to_attr="viewer_votes"))
    return qs


def poll_data(discussion, user):
    try:
        poll = discussion.poll
    except Poll.DoesNotExist:
        return None
    options = list(poll.options.all())
    counts = {option.id: getattr(option, "vote_count", None) for option in options}
    if any(value is None for value in counts.values()):
        counts = dict(PollVote.objects.filter(poll=poll).values_list("option").annotate(n=Count("pk")))
    authenticated = user is not None and user.is_authenticated
    if hasattr(poll, "viewer_votes"):
        mine = [vote.option_id for vote in poll.viewer_votes]
    else:
        mine = list(poll.votes.filter(user=user).values_list("option_id", flat=True)) if authenticated else []
    voters = poll.votes.values("user").distinct().count() if poll.allows_multiple else sum(counts.get(o.id, 0) for o in options)
    show = bool(mine) or poll.is_closed or (authenticated and discussion.author_id == user.id)
    return {
        "id": poll.id,
        "question": poll.question,
        "allows_multiple": poll.allows_multiple,
        "closes_at": poll.closes_at,
        "is_closed": poll.is_closed,
        "total_voters": voters,
        "my_votes": mine,
        "results_visible": show,
        "options": [
            {
                "id": option.id,
                "text": option.text,
                "votes": counts.get(option.id, 0) if show else None,
                "percent": round(100 * counts.get(option.id, 0) / voters) if show and voters else (0 if show else None),
            }
            for option in options
        ],
    }


class PollInputSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=300, trim_whitespace=True)
    options = serializers.ListField(child=serializers.CharField(max_length=100, trim_whitespace=True), min_length=MIN_OPTIONS, max_length=MAX_OPTIONS)
    allows_multiple = serializers.BooleanField(default=False)
    duration_hours = serializers.IntegerField(min_value=MIN_HOURS, max_value=MAX_HOURS, default=24)
    caption = serializers.CharField(max_length=2200, allow_blank=True, required=False, default="")
    category = serializers.CharField(max_length=60, required=False, default="General")
    community = serializers.IntegerField(required=False, allow_null=True)

    def validate_options(self, options):
        cleaned = [option for option in options if option]
        if len(cleaned) < MIN_OPTIONS:
            raise serializers.ValidationError(f"Add at least {MIN_OPTIONS} options.")
        if len({option.casefold() for option in cleaned}) != len(cleaned):
            raise serializers.ValidationError("Each option must be different.")
        return cleaned


class PollCreateView(APIView):
    """POST /posts/poll/ {question, options[], allows_multiple, duration_hours, caption, category, community}."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "uploads"

    def post(self, request):
        from .posts import notify_mentions, reload_post
        from .serializers import DiscussionSerializer

        data = PollInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        post = DiscussionSerializer(
            data={"title": "", "body": values["caption"] or values["question"], "content_html": "",
                  "category": values["category"] or "General", "community": values.get("community")},
            context={"request": request, "allow_untitled": True},
        )
        post.is_valid(raise_exception=True)
        with transaction.atomic():
            discussion = post.save(author=request.user)
            poll = Poll.objects.create(
                discussion=discussion, question=values["question"], allows_multiple=values["allows_multiple"],
                closes_at=timezone.now() + timedelta(hours=values["duration_hours"]),
            )
            PollOption.objects.bulk_create([PollOption(poll=poll, text=text, position=i) for i, text in enumerate(values["options"])])
        notify_mentions(discussion, request.user)
        return Response(reload_post(discussion, request), status=status.HTTP_201_CREATED)


class PollVoteView(APIView):
    """POST {option_ids: [...]} sets your vote (replacing any earlier one); DELETE takes it back."""

    permission_classes = [permissions.IsAuthenticated]

    def get_discussion(self, request, pk):
        from .views import visible_discussions

        discussion = get_object_or_404(visible_discussions(request.user).select_related("poll"), pk=pk)
        try:
            poll = discussion.poll
        except Poll.DoesNotExist:
            return discussion, None
        return discussion, poll

    def respond(self, discussion, request):
        discussion = Discussion.objects.select_related("poll").get(pk=discussion.pk)
        return Response(poll_data(discussion, request.user))

    def post(self, request, pk):
        discussion, poll = self.get_discussion(request, pk)
        if poll is None:
            return Response({"detail": "This post has no poll."}, status=status.HTTP_404_NOT_FOUND)
        if poll.is_closed:
            return Response({"detail": "This poll has closed."}, status=status.HTTP_400_BAD_REQUEST)
        raw = request.data.get("option_ids", [])
        if not isinstance(raw, list):
            raw = [raw]
        try:
            chosen = {int(value) for value in raw}
        except (TypeError, ValueError):
            return Response({"option_ids": ["Choose an option."]}, status=status.HTTP_400_BAD_REQUEST)
        if not chosen:
            return Response({"option_ids": ["Choose an option."]}, status=status.HTTP_400_BAD_REQUEST)
        if len(chosen) > 1 and not poll.allows_multiple:
            return Response({"option_ids": ["This poll allows one choice."]}, status=status.HTTP_400_BAD_REQUEST)
        valid = set(poll.options.filter(pk__in=chosen).values_list("pk", flat=True))
        if valid != chosen:
            return Response({"option_ids": ["That option isn't part of this poll."]}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            PollVote.objects.filter(poll=poll, user=request.user).delete()
            PollVote.objects.bulk_create([PollVote(poll=poll, option_id=option_id, user=request.user) for option_id in sorted(chosen)])
        return self.respond(discussion, request)

    def delete(self, request, pk):
        discussion, poll = self.get_discussion(request, pk)
        if poll is None:
            return Response({"detail": "This post has no poll."}, status=status.HTTP_404_NOT_FOUND)
        if poll.is_closed:
            return Response({"detail": "This poll has closed."}, status=status.HTTP_400_BAD_REQUEST)
        PollVote.objects.filter(poll=poll, user=request.user).delete()
        return self.respond(discussion, request)
