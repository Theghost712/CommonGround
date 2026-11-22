from django.contrib import admin

from .models import ModerationAction


@admin.register(ModerationAction)
class ModerationActionAdmin(admin.ModelAdmin):
    """Read-only audit log: decisions are made in the app's Moderation page."""

    list_display = ["created_at", "action", "moderator", "target_type", "target_id", "target_user", "community", "reports_closed"]
    list_filter = ["action", "target_type", "created_at"]
    search_fields = ["reason", "moderator__username", "target_user__username"]
    readonly_fields = [field.name for field in ModerationAction._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
