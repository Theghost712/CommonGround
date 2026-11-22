from django.contrib import admin

from .models import ConnectionLabel, ContactMatch, Follow


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    list_display = ["follower", "following", "created_at"]
    search_fields = ["follower__username", "following__username"]
    raw_id_fields = ["follower", "following"]


# Labels and contact matches are private to each member; admins see counts, not who.
admin.site.register(ConnectionLabel, list_display=["id", "label", "updated_at"])
admin.site.register(ContactMatch, list_display=["id", "matched_at"])
