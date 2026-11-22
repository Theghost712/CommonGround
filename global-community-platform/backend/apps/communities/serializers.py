from rest_framework import serializers
from .models import Community, CommunityAnnouncement, CommunityMembership, CommunityRule


class CommunitySerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)
    members_count = serializers.SerializerMethodField()
    pending_requests_count = serializers.SerializerMethodField()
    is_member = serializers.SerializerMethodField()
    my_role = serializers.SerializerMethodField()
    membership_status = serializers.SerializerMethodField()

    class Meta:
        model = Community
        fields = [
            "id", "name", "slug", "description", "category", "visibility",
            "logo_url", "cover_url", "created_by", "created_by_username",
            "members_count", "pending_requests_count", "is_member", "my_role",
            "membership_status", "created_at", "updated_at","approval_status",
            "approved_at",
            "rejection_reason",
            "suspension_reason",
        ]
        read_only_fields = [
            "id", "slug", "created_by", "created_by_username", "members_count",
            "pending_requests_count", "is_member", "my_role", "membership_status",
            "created_at", "updated_at","approval_status",
            "approved_at",
            "rejection_reason",
            "suspension_reason",
        ]

    def _membership(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None
        return obj.memberships.filter(user=user).first()

    def get_members_count(self, obj):
        return obj.memberships.filter(status=CommunityMembership.ACTIVE).count()

    def get_pending_requests_count(self, obj):
        membership = self._membership(obj)
        if membership and membership.status == CommunityMembership.ACTIVE and membership.role in [CommunityMembership.OWNER, CommunityMembership.ADMIN]:
            return obj.memberships.filter(status=CommunityMembership.PENDING).count()
        return None

    def get_is_member(self, obj):
        membership = self._membership(obj)
        return bool(membership and membership.status == CommunityMembership.ACTIVE)

    def get_my_role(self, obj):
        membership = self._membership(obj)
        return membership.role if membership and membership.status == CommunityMembership.ACTIVE else None

    def get_membership_status(self, obj):
        membership = self._membership(obj)
        return membership.status if membership else None


class CommunityMembershipSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    display_name = serializers.SerializerMethodField()
    user_id = serializers.IntegerField(source="user.id", read_only=True)

    class Meta:
        model = CommunityMembership
        fields = ["id", "user_id", "username", "display_name", "role", "status", "joined_at", "reviewed_at"]
        read_only_fields = ["id", "user_id", "username", "display_name", "role", "status", "joined_at", "reviewed_at"]

    def get_display_name(self, obj):
        full_name = obj.user.get_full_name().strip()
        return full_name or obj.user.username


class CommunityRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommunityRule
        fields = ["id", "title", "description", "position", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class CommunityAnnouncementSerializer(serializers.ModelSerializer):
    posted_by_username = serializers.CharField(source="posted_by.username", read_only=True)

    class Meta:
        model = CommunityAnnouncement
        fields = ["id", "title", "body", "is_pinned", "posted_by", "posted_by_username", "created_at", "updated_at"]
        read_only_fields = ["id", "posted_by", "posted_by_username", "created_at", "updated_at"]
