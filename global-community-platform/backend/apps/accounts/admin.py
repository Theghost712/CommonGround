from django.contrib import admin

from .models import TwoFactorAuth, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "country", "preferred_language", "updated_at")
    search_fields = ("user__username", "user__email", "country", "interests")
    list_filter = ("preferred_language", "country")


@admin.register(TwoFactorAuth)
class TwoFactorAuthAdmin(admin.ModelAdmin):
    """Support can turn 2FA off for someone who lost their phone and codes (delete the row)."""

    list_display = ("user", "confirmed_at", "updated_at")
    search_fields = ("user__username", "user__email")
    fields = ("user", "confirmed_at", "updated_at")
    readonly_fields = ("user", "confirmed_at", "updated_at")

    def has_add_permission(self, request):
        return False
