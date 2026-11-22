from django.contrib import admin

from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "country", "preferred_language", "updated_at")
    search_fields = ("user__username", "user__email", "country", "interests")
    list_filter = ("preferred_language", "country")
