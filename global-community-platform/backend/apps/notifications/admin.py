from django.contrib import admin
from .models import Notification, NotificationPreference, PushSubscription


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


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    """Devices signed up for push notifications. Deleting one just stops pushes to it."""

    list_display = ["user", "service", "user_agent", "created_at", "last_success_at", "failure_count"]
    list_filter = ["created_at"]
    search_fields = ["user__username", "user_agent"]
    readonly_fields = ["user", "service", "user_agent", "created_at", "last_success_at", "failure_count"]
    exclude = ["endpoint", "p256dh", "auth"]  # capability URL and keys: never shown

    @admin.display(description="Push service")
    def service(self, subscription):
        from urllib.parse import urlparse

        return urlparse(subscription.endpoint).hostname

    def has_add_permission(self, request):
        return False
