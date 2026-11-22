from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import OuterRef, Subquery
from django.utils import timezone
from django.db.models.functions import Lower
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from django.http import Http404
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import UserProfile
from apps.accounts.phone import normalize_phone, phone_hash
from apps.discussions.views import visible_discussions
from apps.notifications.services import notify_follow_accepted, notify_follow_request, notify_new_follower
from apps.safety.models import Block
from apps.safety.services import is_blocked_between

from .models import ConnectionLabel, ContactMatch, Follow, FollowRequest
from .serializers import ContactMatchRequestSerializer, LabelSerializer, PersonSerializer, ProfileDetailSerializer
from .services import people_queryset, relationship_map, search_people, suggestions_for

User = get_user_model()


class PeoplePagination(PageNumberPagination):
    page_size = 20


def _people_response(view, request, queryset, extra_context=None):
    paginator = PeoplePagination()
    page = paginator.paginate_queryset(queryset, request, view=view)
    context = {"relations": relationship_map(request.user, [user.pk for user in page]), **(extra_context or {})}
    return paginator.get_paginated_response(PersonSerializer(page, many=True, context=context).data)


def _target(username):
    return get_object_or_404(people_queryset(), username=username)


def _visible_target(request, username):
    """The person, unless they have blocked the viewer (then they simply don't exist)."""
    user = _target(username)
    if Block.objects.filter(blocker=user, blocked=request.user).exists():
        raise Http404
    return user


def _require_can_view(request, user):
    relation = relationship_map(request.user, [user.pk]).get(user.pk, {})
    if relation.get("blocked") or not relation.get("can_view", True):
        raise PermissionDenied("This account is private.")


class PeopleSearchView(APIView):
    """GET /people/?search=… — find members by name or username (never by email or phone)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        query = request.query_params.get("search", "").strip()
        if len(query) < 2:
            return Response({"count": 0, "next": None, "previous": None, "results": []})
        return _people_response(self, request, search_people(request.user, query))


class SuggestionsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        pairs = suggestions_for(request.user)
        users = [user for user, _ in pairs]
        context = {
            "relations": relationship_map(request.user, [user.pk for user in users]),
            "reasons": {user.pk: reason for user, reason in pairs},
        }
        return Response(PersonSerializer(users, many=True, context=context).data)


class StoriesView(APIView):
    """People you follow, most recently active first, for the stories row on the home feed.

    `has_new` marks anyone who posted in the last 24 hours; `latest_discussion_id`
    is the post a story bubble opens.
    """

    permission_classes = [permissions.IsAuthenticated]
    LIMIT = 24

    def get(self, request):
        visible = visible_discussions(request.user)
        latest = visible.filter(author=OuterRef("pk")).order_by("-created_at")
        users = list(
            people_queryset()
            .filter(follower_links__follower=request.user)
            .annotate(
                latest_post_at=Subquery(latest.values("created_at")[:1]),
                latest_discussion_id=Subquery(latest.values("id")[:1]),
            )
            .order_by("-latest_post_at", "-follower_links__created_at")[: self.LIMIT]
        )
        since = timezone.now() - timedelta(hours=24)
        relations = relationship_map(request.user, [user.pk for user in users])
        people = PersonSerializer(users, many=True, context={"relations": relations}).data
        for person, user in zip(people, users):
            person["latest_post_at"] = user.latest_post_at
            person["latest_discussion_id"] = user.latest_discussion_id
            person["has_new"] = bool(user.latest_post_at and user.latest_post_at >= since)
        return Response(people)


class PersonDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, username):
        user = _visible_target(request, username)
        context = {
            "relations": relationship_map(request.user, [user.pk]),
            "discussions_count": visible_discussions(request.user).filter(author=user).count(),
        }
        return Response(ProfileDetailSerializer(user, context=context).data)


class FollowView(APIView):
    """POST follows, DELETE unfollows. Both are idempotent."""

    permission_classes = [permissions.IsAuthenticated]

    def _respond(self, request, user, code=status.HTTP_200_OK):
        user = _target(user.username)  # refresh counts
        return Response(
            PersonSerializer(user, context={"relations": relationship_map(request.user, [user.pk])}).data,
            status=code,
        )

    def post(self, request, username):
        user = _visible_target(request, username)
        if user.pk == request.user.pk:
            raise ValidationError({"detail": "You cannot follow yourself."})
        if is_blocked_between(request.user, user):
            raise PermissionDenied("Unblock this account to follow it.")
        if Follow.objects.filter(follower=request.user, following=user).exists():
            return self._respond(request, user)
        if getattr(getattr(user, "profile", None), "is_private", False):
            follow_request, created = FollowRequest.objects.get_or_create(requester=request.user, target=user)
            if created:
                notify_follow_request(follow_request)
            return self._respond(request, user, status.HTTP_202_ACCEPTED)
        try:
            with transaction.atomic():
                follow, created = Follow.objects.get_or_create(follower=request.user, following=user)
        except IntegrityError:
            created = False
        if created:
            notify_new_follower(follow)
        return self._respond(request, user, status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def delete(self, request, username):
        user = _target(username)
        Follow.objects.filter(follower=request.user, following=user).delete()
        FollowRequest.objects.filter(requester=request.user, target=user).delete()  # also cancels a pending request
        return self._respond(request, user)


class FollowRequestsView(APIView):
    """Incoming requests to follow a private account: list, approve, decline."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        queryset = people_queryset().filter(follow_requests_sent__target=request.user).order_by("-follow_requests_sent__created_at")
        return _people_response(self, request, queryset)

    def post(self, request, username, action):
        requester = _target(username)
        follow_request = get_object_or_404(FollowRequest, requester=requester, target=request.user)
        follow_request.delete()
        if action == "approve":
            Follow.objects.get_or_create(follower=requester, following=request.user)
            notify_follow_accepted(request.user, requester)
        return Response({"username": requester.username, "approved": action == "approve"})


class FollowersView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, username):
        user = _visible_target(request, username)
        _require_can_view(request, user)
        queryset = people_queryset().filter(following_links__following=user).order_by("-following_links__created_at")
        return _people_response(self, request, queryset)


class FollowingView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, username):
        user = _visible_target(request, username)
        _require_can_view(request, user)
        queryset = people_queryset().filter(follower_links__follower=user).order_by("-follower_links__created_at")
        return _people_response(self, request, queryset)


class LabelView(APIView):
    """A private relationship tag (Family, Friend, …) only the requesting user can see."""

    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, username):
        user = _target(username)
        if user.pk == request.user.pk:
            raise ValidationError({"detail": "You cannot label yourself."})
        serializer = LabelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ConnectionLabel.objects.update_or_create(owner=request.user, target=user, defaults={"label": serializer.validated_data["label"]})
        return Response({"label": serializer.validated_data["label"]})

    def delete(self, request, username):
        user = _target(username)
        ConnectionLabel.objects.filter(owner=request.user, target=user).delete()
        return Response({"label": None})


class ContactMatchView(APIView):
    """Match phone-book entries to members who opted in to being found.

    The submitted numbers and emails are used for this lookup only and are not stored;
    only the resulting matches are remembered (to show "In your contacts").
    """

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "contacts"

    def post(self, request):
        serializer = ContactMatchRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        hashes = {phone_hash(n) for n in (normalize_phone(raw) for raw in serializer.validated_data["phones"]) if n}
        emails = {email.strip().lower() for email in serializer.validated_data["emails"] if "@" in email}

        discoverable = UserProfile.objects.filter(discoverable_by_contacts=True, user__is_active=True).exclude(user=request.user)
        matched_ids = set()
        if hashes:
            matched_ids |= set(discoverable.filter(phone_hash__in=hashes).values_list("user_id", flat=True))
        if emails:
            matched_ids |= set(
                discoverable.annotate(email_lower=Lower("user__email")).filter(email_lower__in=emails).values_list("user_id", flat=True)
            )
        for user_id in matched_ids:
            ContactMatch.objects.update_or_create(owner=request.user, target_id=user_id)

        users = list(people_queryset().filter(pk__in=matched_ids).order_by("first_name", "username"))
        context = {"relations": relationship_map(request.user, [user.pk for user in users])}
        return Response({
            "checked": len(hashes) + len(emails),
            "matches": PersonSerializer(users, many=True, context=context).data,
        })
