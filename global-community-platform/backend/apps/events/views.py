from django.db.models import Q
from django.shortcuts import get_object_or_404

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.communities.models import Community, CommunityMembership

from .models import CommunityEvent, EventRSVP
from .serializers import CommunityEventSerializer, EventRSVPSerializer

from apps.notifications.services import (
    notify_event_created,
    notify_event_updated,
    notify_event_cancelled,
    notify_event_rsvp,
)


class CommunityEventViewSet(viewsets.ModelViewSet):
    serializer_class = CommunityEventSerializer
    permission_classes = [permissions.IsAuthenticated]

    search_fields = [
        "title",
        "description",
        "location",
        "community__name",
    ]

    ordering_fields = [
        "starts_at",
        "created_at",
        "title",
    ]

    def get_queryset(self):
        user = self.request.user

        if not user.is_authenticated:
            return CommunityEvent.objects.none()

        queryset = CommunityEvent.objects.select_related(
            "community",
            "created_by",
        ).prefetch_related("rsvps")

        # Public and restricted communities are visible.
        # Private community events are visible only to active members.
        visibility = Q(
            community__visibility__in=[
                Community.PUBLIC,
                Community.RESTRICTED,
            ]
        )

        visibility |= Q(
            community__memberships__user=user,
            community__memberships__status=CommunityMembership.ACTIVE,
        )

        queryset = queryset.filter(
            community__approval_status=Community.APPROVED,
        ).filter(visibility).distinct()

        community_id = self.request.query_params.get("community")
        if community_id:
            queryset = queryset.filter(community_id=community_id)

        event_status = self.request.query_params.get("status")
        if event_status:
            queryset = queryset.filter(status=event_status)

        return queryset

    def _require_active_member(self, community):
        membership = CommunityMembership.objects.filter(
            community=community,
            user=self.request.user,
            status=CommunityMembership.ACTIVE,
        ).first()

        if not membership:
            raise PermissionDenied(
                "You must be an active community member to perform this action."
            )

        return membership

    def _require_manager(self, community):
        if community.approval_status != Community.APPROVED:
            raise PermissionDenied("Events are available only after the community is approved.")
        membership = self._require_active_member(community)

        allowed_roles = [
            CommunityMembership.OWNER,
            CommunityMembership.ADMIN,
            CommunityMembership.MODERATOR,
        ]

        if membership.role not in allowed_roles:
            raise PermissionDenied(
                "Only community owners, administrators and moderators can manage events."
            )

        return membership

    def perform_create(self, serializer):
        community = serializer.validated_data["community"]

        self._require_manager(community)

        event = serializer.save(created_by=self.request.user)
        notify_event_created(event)

    def perform_update(self, serializer):
        event = self.get_object()

        self._require_manager(event.community)

        new_community = serializer.validated_data.get(
            "community",
            event.community,
        )

        if new_community.pk != event.community_id:
            self._require_manager(new_community)

        previous_values = {
            "community_id": event.community_id,
            "title": event.title,
            "description": event.description,
            "location": event.location,
            "starts_at": event.starts_at,
            "ends_at": event.ends_at,
            "status": event.status,
        }

        updated_event = serializer.save()

        changed = any(
            getattr(updated_event, field) != value
            for field, value in previous_values.items()
        )

        if changed:
            notify_event_updated(updated_event, self.request.user)

    def perform_destroy(self, instance):
        self._require_manager(instance.community)
        instance.delete()

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[permissions.IsAuthenticated],
    )
    def cancel(self, request, pk=None):
        event = self.get_object()

        self._require_manager(event.community)

        if event.status == CommunityEvent.CANCELLED:
            return Response({
                "detail": "This event is already cancelled."
            })

        event.status = CommunityEvent.CANCELLED
        event.save(update_fields=["status", "updated_at"])
        notify_event_cancelled(event, request.user)

        return Response(
            CommunityEventSerializer(
                event,
                context={"request": request},
            ).data
        )

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[permissions.IsAuthenticated],
    )
    def rsvp(self, request, pk=None):
        event = self.get_object()

        self._require_active_member(event.community)

        if event.status == CommunityEvent.CANCELLED:
            raise ValidationError(
                {"detail": "You cannot RSVP to a cancelled event."}
            )

        serializer = EventRSVPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        existing_rsvp = EventRSVP.objects.filter(
            event=event,
            user=request.user,
        ).first()

        previous_response = (
            existing_rsvp.response if existing_rsvp else None
        )

        rsvp, created = EventRSVP.objects.update_or_create(
            event=event,
            user=request.user,
            defaults={
                "response": serializer.validated_data["response"],
            },
        )

        if created or previous_response != rsvp.response:
            notify_event_rsvp(rsvp)

        response_status = (
            status.HTTP_201_CREATED
            if created
            else status.HTTP_200_OK
        )

        return Response(
            EventRSVPSerializer(rsvp).data,
            status=response_status,
        )

    @action(
        detail=True,
        methods=["get"],
        permission_classes=[permissions.IsAuthenticated],
    )
    def attendees(self, request, pk=None):
        event = self.get_object()

        self._require_active_member(event.community)

        attendees = event.rsvps.select_related(
            "user"
        ).order_by("-responded_at")

        return Response(
            EventRSVPSerializer(attendees, many=True).data
        )
