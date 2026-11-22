from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import permissions, serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.social.models import Follow
from apps.social.serializers import PersonSerializer
from apps.social.services import people_queryset, relationship_map

from .models import Block, Mute, Report

User = get_user_model()


def _person_list(request, user_ids):
    users = list(people_queryset().filter(pk__in=list(user_ids)).order_by("username"))
    return PersonSerializer(users, many=True, context={"relations": relationship_map(request.user, [u.pk for u in users])}).data


def _other(request, username):
    other = get_object_or_404(User, username=username, is_active=True)
    if other.pk == request.user.pk:
        raise ValidationError({"detail": "You can't do that to yourself."})
    return other


class BlockView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(_person_list(request, Block.objects.filter(blocker=request.user).values_list("blocked_id", flat=True)))

    def put(self, request, username):
        other = _other(request, username)
        with transaction.atomic():
            Block.objects.get_or_create(blocker=request.user, blocked=other)
            # Blocking cuts every tie in both directions.
            Follow.objects.filter(Q(follower=request.user, following=other) | Q(follower=other, following=request.user)).delete()
            from apps.stories.models import CloseFriend

            CloseFriend.objects.filter(Q(owner=request.user, friend=other) | Q(owner=other, friend=request.user)).delete()
            from apps.social.models import FollowRequest

            FollowRequest.objects.filter(Q(requester=request.user, target=other) | Q(requester=other, target=request.user)).delete()
        return Response({"username": other.username, "blocked": True})

    def delete(self, request, username):
        other = get_object_or_404(User, username=username)
        Block.objects.filter(blocker=request.user, blocked=other).delete()
        return Response({"username": other.username, "blocked": False})


class MuteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(_person_list(request, Mute.objects.filter(owner=request.user).values_list("muted_id", flat=True)))

    def put(self, request, username):
        other = _other(request, username)
        posts = bool(request.data.get("posts", True))
        stories = bool(request.data.get("stories", True))
        if not posts and not stories:
            Mute.objects.filter(owner=request.user, muted=other).delete()
            return Response({"username": other.username, "posts": False, "stories": False})
        Mute.objects.update_or_create(owner=request.user, muted=other, defaults={"mute_posts": posts, "mute_stories": stories})
        return Response({"username": other.username, "posts": posts, "stories": stories})

    def delete(self, request, username):
        other = get_object_or_404(User, username=username)
        Mute.objects.filter(owner=request.user, muted=other).delete()
        return Response({"username": other.username, "posts": False, "stories": False})


class ReportSerializer(serializers.Serializer):
    target_type = serializers.ChoiceField(choices=Report.TARGETS)
    target_id = serializers.IntegerField(min_value=1)
    reason = serializers.ChoiceField(choices=Report.REASONS)
    details = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


def resolve_target_owner(viewer, target_type, target_id):
    """Return the owner of a reportable thing the viewer can actually see, or None."""
    if target_type == Report.USER:
        return User.objects.filter(pk=target_id, is_active=True).first()
    if target_type == Report.POST:
        from apps.discussions.views import visible_discussions

        post = visible_discussions(viewer).filter(pk=target_id).select_related("author").first()
        return post.author if post else None
    if target_type == Report.COMMENT:
        from apps.discussions.models import Comment
        from apps.discussions.views import visible_discussions

        comment = Comment.objects.filter(pk=target_id, discussion__in=visible_discussions(viewer)).select_related("author").first()
        return comment.author if comment else None
    if target_type == Report.STORY:
        from apps.stories.access import visible_stories

        story = visible_stories(viewer).filter(pk=target_id).select_related("author").first()
        return story.author if story else None
    if target_type == Report.MESSAGE:
        from apps.messaging.models import Message

        message = Message.objects.filter(pk=target_id, conversation__memberships__user=viewer, conversation__memberships__is_active=True).select_related("sender").first()
        return message.sender if message else None
    return None


class ReportView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "reports"

    def post(self, request):
        serializer = ReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        owner = resolve_target_owner(request.user, data["target_type"], data["target_id"])
        if owner is None:
            raise ValidationError({"target_id": "We couldn't find that, or you can't see it."})
        if owner.pk == request.user.pk:
            raise ValidationError({"target_id": "You can't report your own content."})
        report, created = Report.objects.get_or_create(
            reporter=request.user, target_type=data["target_type"], target_id=data["target_id"],
            defaults={"reason": data["reason"], "details": data["details"].strip(), "target_owner": owner},
        )
        return Response(
            {"reported": True, "already_reported": not created, "message": "Thanks for letting us know. Reports are anonymous."},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
