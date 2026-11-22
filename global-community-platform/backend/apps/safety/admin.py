from django.contrib import admin
from django.utils import timezone

from .models import Block, Mute, Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ["id", "target_type", "target_id", "target_owner", "reason", "status", "created_at"]
    list_filter = ["status", "target_type", "reason"]
    search_fields = ["target_owner__username", "details"]
    readonly_fields = ["reporter", "target_type", "target_id", "target_owner", "reason", "details", "created_at", "reviewed_by", "reviewed_at"]
    actions = ["mark_actioned", "mark_dismissed"]

    def _review(self, request, queryset, status):
        updated = queryset.update(status=status, reviewed_by=request.user, reviewed_at=timezone.now())
        self.message_user(request, f"{updated} report(s) updated.")

    @admin.action(description="Mark as action taken")
    def mark_actioned(self, request, queryset):
        self._review(request, queryset, Report.ACTIONED)

    @admin.action(description="Mark as no violation")
    def mark_dismissed(self, request, queryset):
        self._review(request, queryset, Report.DISMISSED)


admin.site.register(Block, list_display=["id", "created_at"])
admin.site.register(Mute, list_display=["id", "created_at"])
