from django.contrib import admin

from .models import CommunityEvent, EventReminder, EventRSVP


class EventRSVPInline(admin.TabularInline):
    model = EventRSVP
    extra = 0
    fields = ("user", "response", "responded_at")
    readonly_fields = ("responded_at",)


class EventReminderInline(admin.TabularInline):
    model = EventReminder
    extra = 0
    fields = ("user", "reminder_type", "sent_at")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(CommunityEvent)
class CommunityEventAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "community",
        "status",
        "starts_at",
        "ends_at",
        "created_by",
        "created_at",
    )
    list_filter = ("status", "starts_at", "community__visibility", "community__category")
    search_fields = (
        "title",
        "description",
        "location",
        "community__name",
        "created_by__username",
    )
    date_hierarchy = "starts_at"
    readonly_fields = ("created_by", "created_at", "updated_at")
    list_select_related = ("community", "created_by")
    inlines = (EventRSVPInline, EventReminderInline)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(EventRSVP)
class EventRSVPAdmin(admin.ModelAdmin):
    list_display = ("event", "user", "response", "responded_at")
    list_filter = ("response", "responded_at", "event__community__category")
    search_fields = (
        "event__title",
        "event__community__name",
        "user__username",
        "user__email",
    )
    date_hierarchy = "responded_at"
    readonly_fields = ("responded_at",)
    list_select_related = ("event", "event__community", "user")


@admin.register(EventReminder)
class EventReminderAdmin(admin.ModelAdmin):
    list_display = ("event", "user", "reminder_type", "sent_at")
    list_filter = ("reminder_type", "sent_at", "event__community__category")
    search_fields = (
        "event__title",
        "event__community__name",
        "user__username",
        "user__email",
    )
    date_hierarchy = "sent_at"
    readonly_fields = ("event", "user", "reminder_type", "sent_at")
    list_select_related = ("event", "event__community", "user")

    def has_add_permission(self, request):
        return False
