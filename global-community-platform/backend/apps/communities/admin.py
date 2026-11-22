from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from .access import community_is_unused
from .models import (
    Community,
    CommunityAnnouncement,
    CommunityMembership,
    CommunityRule,
)


class CommunityMembershipInline(admin.TabularInline):
    model = CommunityMembership
    extra = 0


class CommunityRuleInline(admin.TabularInline):
    model = CommunityRule
    extra = 0


class CommunityAnnouncementInline(admin.TabularInline):
    model = CommunityAnnouncement
    extra = 0
    readonly_fields = ["posted_by", "created_at", "updated_at"]


@admin.register(Community)
class CommunityAdmin(admin.ModelAdmin):

    list_display = [
        "name",
        "category",
        "visibility",
        "approval_status",
        "created_by",
        "approved_by",
        "created_at",
    ]

    list_filter = [
        "approval_status",
        "visibility",
        "category",
        "created_at",
    ]

    search_fields = [
        "name",
        "description",
        "created_by__username",
        "approved_by__username",
    ]

    readonly_fields = [
        "created_at",
        "updated_at",
        "approved_by",
        "approved_at",
        "approval_status",
    ]

    inlines = [
        CommunityMembershipInline,
        CommunityRuleInline,
        CommunityAnnouncementInline,
    ]

    actions = [
        "approve_communities",
        "reject_communities",
        "suspend_communities",
        "restore_communities",
    ]

    def has_delete_permission(self, request, obj=None):
        allowed = super().has_delete_permission(request, obj)
        return allowed and (obj is None or community_is_unused(obj))

    @transaction.atomic
    def delete_model(self, request, obj):
        if not community_is_unused(obj):
            raise PermissionDenied("Communities with discussions, events, announcements, rules, or other members cannot be deleted.")
        super().delete_model(request, obj)

    @admin.action(
        permissions=["change"],
        description="Approve selected communities",
    )
    @transaction.atomic
    def approve_communities(self, request, queryset):
        count = 0
        now = timezone.now()

        for community in queryset:
            if community.approval_status in [
                Community.PENDING,
                Community.REJECTED,
            ]:
                community.approval_status = Community.APPROVED
                community.approved_by = request.user
                community.approved_at = now
                community.rejection_reason = ""
                community.suspension_reason = ""

                community.save(update_fields=[
                    "approval_status",
                    "approved_by",
                    "approved_at",
                    "rejection_reason",
                    "suspension_reason",
                    "updated_at",
                ])

                count += 1

        self.message_user(
            request,
            f"{count} communities approved successfully.",
            messages.SUCCESS,
        )

    @admin.action(
        permissions=["change"],
        description="Reject selected communities",
    )
    @transaction.atomic
    def reject_communities(self, request, queryset):
        count = 0

        for community in queryset:
            if community.approval_status == Community.PENDING:
                community.approval_status = Community.REJECTED
                community.approved_by = None
                community.approved_at = None

                community.save(update_fields=[
                    "approval_status",
                    "approved_by",
                    "approved_at",
                    "updated_at",
                ])

                count += 1

        self.message_user(
            request,
            f"{count} communities rejected.",
            messages.WARNING,
        )

    @admin.action(
        permissions=["change"],
        description="Suspend selected communities",
    )
    @transaction.atomic
    def suspend_communities(self, request, queryset):
        count = 0

        for community in queryset:
            if community.approval_status == Community.APPROVED:
                community.approval_status = Community.SUSPENDED

                community.save(update_fields=[
                    "approval_status",
                    "updated_at",
                ])

                count += 1

        self.message_user(
            request,
            f"{count} communities suspended.",
            messages.WARNING,
        )

    @admin.action(
        permissions=["change"],
        description="Restore suspended communities",
    )
    @transaction.atomic
    def restore_communities(self, request, queryset):
        count = 0
        now = timezone.now()

        for community in queryset:
            if community.approval_status == Community.SUSPENDED:
                community.approval_status = Community.APPROVED
                community.approved_by = request.user
                community.approved_at = now
                community.suspension_reason = ""

                community.save(update_fields=[
                    "approval_status",
                    "approved_by",
                    "approved_at",
                    "suspension_reason",
                    "updated_at",
                ])

                count += 1

        self.message_user(
            request,
            f"{count} communities restored successfully.",
            messages.SUCCESS,
        )


@admin.register(CommunityMembership)
class CommunityMembershipAdmin(admin.ModelAdmin):
    list_display = [
        "community",
        "user",
        "role",
        "status",
        "joined_at",
        "reviewed_by",
    ]

    list_filter = ["status", "role", "joined_at"]
    search_fields = ["community__name", "user__username"]


@admin.register(CommunityRule)
class CommunityRuleAdmin(admin.ModelAdmin):
    list_display = ["title", "community", "position", "updated_at"]
    search_fields = ["title", "community__name"]


@admin.register(CommunityAnnouncement)
class CommunityAnnouncementAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "community",
        "posted_by",
        "is_pinned",
        "created_at",
    ]

    list_filter = ["is_pinned", "created_at"]
    search_fields = ["title", "body", "community__name"]
