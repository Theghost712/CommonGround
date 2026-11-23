from django.contrib import admin

from .models import Call


@admin.register(Call)
class CallAdmin(admin.ModelAdmin):
    list_display = ["created_at", "kind", "caller", "callee", "status", "answered_at", "ended_at"]
    list_filter = ["kind", "status"]
    search_fields = ["caller__username", "callee__username"]
    readonly_fields = [field.name for field in Call._meta.fields]


from .models import GroupCall, GroupCallParticipant


class GroupCallParticipantInline(admin.TabularInline):
    model = GroupCallParticipant
    extra = 0
    readonly_fields = ["user", "device_id", "joined_at", "last_seen", "left_at"]
    can_delete = False


@admin.register(GroupCall)
class GroupCallAdmin(admin.ModelAdmin):
    list_display = ["created_at", "kind", "conversation", "started_by", "status", "ended_at"]
    list_filter = ["kind", "status"]
    readonly_fields = ["conversation", "started_by", "kind", "status", "created_at", "ended_at"]
    inlines = [GroupCallParticipantInline]
