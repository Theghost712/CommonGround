from django.contrib import admin
from .models import Notification, NotificationPreference


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["recipient", "notification_type", "title", "is_read", "created_at"]
    list_filter = ["notification_type", "is_read", "created_at"]
    search_fields = ["recipient__username", "actor__username", "title", "body"]
    readonly_fields = ["created_at", "read_at"]


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ["user", "messages_enabled", "discussions_enabled", "communities_enabled", "mentions_enabled"]
    search_fields = ["user__username", "user__email"]
