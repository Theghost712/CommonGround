from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .models import Community, CommunityAnnouncement, CommunityMembership, CommunityRule
from .access import community_is_unused
from .permissions import has_community_role, has_platform_community_permission
from apps.notifications.services import notify_membership_request, notify_membership_approved, notify_community_announcement

from .serializers import (
    CommunityAnnouncementSerializer,
    CommunityMembershipSerializer,
    CommunityRuleSerializer,
    CommunitySerializer,
)


class CommunityViewSet(viewsets.ModelViewSet):
    serializer_class = CommunitySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    search_fields = ["name", "description", "category"]
    ordering_fields = ["created_at", "name"]

    def get_queryset(self):
        qs = Community.objects.select_related(
            "created_by"
        ).prefetch_related("memberships")

        user = self.request.user

        # System Admin can see all communities
        if has_platform_community_permission(user):
            visible = Q()
        else:
            # Only approved public and restricted communities
            visible = Q(
                approval_status=Community.APPROVED,
                visibility__in=[
                    Community.PUBLIC,
                    Community.RESTRICTED,
                ],
            )

            if user.is_authenticated:
                # Approved private communities are visible to active members
                visible |= Q(
                    approval_status=Community.APPROVED,
                    memberships__user=user,
                    memberships__status=CommunityMembership.ACTIVE,
                )

                # Owners can see their own communities, including pending ones
                visible |= Q(created_by=user)

        qs = qs.filter(visible).distinct()

        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category__iexact=category)

        return qs

    def _membership(self, community, user=None):
        return community.memberships.filter(
            user=user or self.request.user
        ).first()

    def _require_manager(self, community, include_moderator=False):
        allowed = [
            CommunityMembership.OWNER,
            CommunityMembership.ADMIN,
        ]

        if include_moderator:
            allowed.append(CommunityMembership.MODERATOR)

        if not has_community_role(self.request.user, community, allowed):
            raise PermissionDenied(
                "You do not have permission to manage this community."
            )
        return self._membership(community)

    def perform_create(self, serializer):
        with transaction.atomic():
            community = serializer.save(
                created_by=self.request.user,
                approval_status=Community.PENDING,
            )

            CommunityMembership.objects.create(
                community=community,
                user=self.request.user,
                role=CommunityMembership.OWNER,
                status=CommunityMembership.ACTIVE,
            )

    def perform_update(self, serializer):
        community = self.get_object()
        if not has_platform_community_permission(self.request.user, "change_community"):
            self._require_manager(community)
        serializer.save()

    def perform_destroy(self, instance):
        if not has_platform_community_permission(self.request.user, "delete_community"):
            raise PermissionDenied("Only a platform administrator can delete a community.")
        if self.request.query_params.get("confirm_id") != str(instance.pk):
            raise ValidationError({"confirm_id": "Pass the community ID as confirm_id to confirm deletion."})
        with transaction.atomic():
            community = Community.objects.select_for_update().get(pk=instance.pk)
            if not community_is_unused(community):
                raise ValidationError({"detail": "Communities with discussions, events, announcements, rules, or other members cannot be deleted."})
            community.delete()

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def join(self, request, pk=None):
        community = self.get_object()
        if community.visibility == Community.PRIVATE:
            return Response({"detail": "Private communities are invitation-only. Ask a community administrator for an invitation."}, status=status.HTTP_403_FORBIDDEN)
        membership = self._membership(community)
        if membership and membership.status == CommunityMembership.ACTIVE:
            return Response({"joined": True, "status": "active", "role": membership.role})

        if community.visibility == Community.PUBLIC:
            if membership:
                membership.status = CommunityMembership.ACTIVE
                membership.role = CommunityMembership.MEMBER
                membership.reviewed_at = None
                membership.reviewed_by = None
                membership.save(update_fields=["status", "role", "reviewed_at", "reviewed_by"])
            else:
                membership = CommunityMembership.objects.create(community=community, user=request.user)
            return Response({"joined": True, "status": "active", "role": membership.role})

        if membership and membership.status == CommunityMembership.PENDING:
            return Response({"joined": False, "status": "pending", "detail": "Your membership request is awaiting approval."})
        if membership:
            membership.status = CommunityMembership.PENDING
            membership.role = CommunityMembership.MEMBER
            membership.reviewed_at = None
            membership.reviewed_by = None
            membership.save(update_fields=["status", "role", "reviewed_at", "reviewed_by"])
        else:
            membership = CommunityMembership.objects.create(community=community, user=request.user, status=CommunityMembership.PENDING)
        notify_membership_request(community, request.user)
        return Response({"joined": False, "status": "pending", "detail": "Your request has been sent to the community moderators."}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated])
    def leave(self, request, pk=None):
        community = self.get_object()
        membership = self._membership(community)
        if not membership:
            return Response({"detail": "You do not have a membership or pending request."}, status=status.HTTP_400_BAD_REQUEST)
        if membership.status == CommunityMembership.ACTIVE and membership.role == CommunityMembership.OWNER:
            return Response({"detail": "The owner cannot leave before transferring ownership or deleting the community."}, status=status.HTTP_400_BAD_REQUEST)
        membership.delete()
        return Response({"joined": False, "status": "none"})

    @action(detail=True, methods=["get"], permission_classes=[permissions.AllowAny])
    def members(self, request, pk=None):
        community = self.get_object()
        membership = self._membership(community) if request.user.is_authenticated else None
        if community.visibility == Community.PRIVATE and not (membership and membership.status == CommunityMembership.ACTIVE):
            raise PermissionDenied("You must be a member to view this community's members.")
        members = community.memberships.filter(status=CommunityMembership.ACTIVE).select_related("user")
        return Response(CommunityMembershipSerializer(members, many=True).data)

    @action(detail=True, methods=["get"], permission_classes=[permissions.IsAuthenticated], url_path="membership-requests")
    def membership_requests(self, request, pk=None):
        community = self.get_object()
        self._require_manager(community)
        requests = community.memberships.filter(status=CommunityMembership.PENDING).select_related("user")
        return Response(CommunityMembershipSerializer(requests, many=True).data)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated], url_path="approve-request")
    def approve_request(self, request, pk=None):
        community = self.get_object()
        self._require_manager(community)
        membership = get_object_or_404(community.memberships.select_related("user"), pk=request.data.get("membership_id"), status=CommunityMembership.PENDING)
        membership.approve(request.user)
        notify_membership_approved(membership, request.user)
        return Response(CommunityMembershipSerializer(membership).data)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated], url_path="reject-request")
    def reject_request(self, request, pk=None):
        community = self.get_object()
        self._require_manager(community)
        membership = get_object_or_404(community.memberships.select_related("user"), pk=request.data.get("membership_id"), status=CommunityMembership.PENDING)
        membership.reject(request.user)
        return Response({"rejected": True, "membership_id": membership.id})

    @action(detail=True, methods=["patch"], permission_classes=[permissions.IsAuthenticated], url_path="update-member-role")
    def update_member_role(self, request, pk=None):
        community = self.get_object()
        actor = self._require_manager(community)
        target = get_object_or_404(community.memberships.select_related("user"), pk=request.data.get("membership_id"), status=CommunityMembership.ACTIVE)
        new_role = request.data.get("role")
        allowed = {CommunityMembership.MEMBER, CommunityMembership.MODERATOR}
        if actor.role == CommunityMembership.OWNER:
            allowed.add(CommunityMembership.ADMIN)
        if new_role not in allowed:
            raise ValidationError({"role": "This role cannot be assigned by your account."})
        if target.role == CommunityMembership.OWNER:
            raise ValidationError({"detail": "The community owner role cannot be changed here."})
        if actor.role == CommunityMembership.ADMIN and target.role == CommunityMembership.ADMIN:
            raise PermissionDenied("Administrators cannot change another administrator's role.")
        target.role = new_role
        target.save(update_fields=["role"])
        return Response(CommunityMembershipSerializer(target).data)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated], url_path="remove-member")
    def remove_member(self, request, pk=None):
        community = self.get_object()
        actor = self._require_manager(community, include_moderator=True)
        target = get_object_or_404(community.memberships.select_related("user"), pk=request.data.get("membership_id"), status=CommunityMembership.ACTIVE)
        if target.role == CommunityMembership.OWNER:
            raise ValidationError({"detail": "The community owner cannot be removed."})
        if target.user_id == request.user.id:
            raise ValidationError({"detail": "Use the leave community action to remove yourself."})
        if actor.role == CommunityMembership.MODERATOR and target.role != CommunityMembership.MEMBER:
            raise PermissionDenied("Moderators can only remove regular members.")
        if actor.role == CommunityMembership.ADMIN and target.role == CommunityMembership.ADMIN:
            raise PermissionDenied("Administrators cannot remove another administrator.")
        target.delete()
        return Response({"removed": True})

    @action(detail=True, methods=["get", "post"], permission_classes=[permissions.IsAuthenticatedOrReadOnly])
    def rules(self, request, pk=None):
        community = self.get_object()
        if request.method == "GET":
            return Response(CommunityRuleSerializer(community.rules.all(), many=True).data)
        self._require_manager(community, include_moderator=True)
        serializer = CommunityRuleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rule = serializer.save(community=community)
        return Response(CommunityRuleSerializer(rule).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch", "delete"], permission_classes=[permissions.IsAuthenticated], url_path=r"rules/(?P<rule_id>\d+)")
    def rule_detail(self, request, pk=None, rule_id=None):
        community = self.get_object()
        self._require_manager(community, include_moderator=True)
        rule = get_object_or_404(community.rules, pk=rule_id)
        if request.method == "DELETE":
            rule.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        serializer = CommunityRuleSerializer(rule, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=["get", "post"], permission_classes=[permissions.IsAuthenticatedOrReadOnly])
    def announcements(self, request, pk=None):
        community = self.get_object()
        if request.method == "GET":
            return Response(CommunityAnnouncementSerializer(community.announcements.select_related("posted_by"), many=True).data)
        self._require_manager(community, include_moderator=True)
        serializer = CommunityAnnouncementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        announcement = serializer.save(community=community, posted_by=request.user)
        notify_community_announcement(announcement)
        return Response(CommunityAnnouncementSerializer(announcement).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch", "delete"], permission_classes=[permissions.IsAuthenticated], url_path=r"announcements/(?P<announcement_id>\d+)")
    def announcement_detail(self, request, pk=None, announcement_id=None):
        community = self.get_object()
        self._require_manager(community, include_moderator=True)
        announcement = get_object_or_404(community.announcements, pk=announcement_id)
        if request.method == "DELETE":
            announcement.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        serializer = CommunityAnnouncementSerializer(announcement, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
