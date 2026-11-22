from django.contrib import admin

from .models import Story


@admin.register(Story)
class StoryAdmin(admin.ModelAdmin):
    list_display = ["id", "author", "media_type", "audience", "view_count", "created_at", "expires_at"]
    list_filter = ["media_type", "audience"]
    search_fields = ["author__username"]
    raw_id_fields = ["author"]
    readonly_fields = ["view_count", "created_at"]
