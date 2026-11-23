from django.contrib import admin
from .models import Comment, Discussion, DiscussionAttachment, DiscussionBookmark, DiscussionReaction


class DiscussionAttachmentInline(admin.TabularInline):
    model = DiscussionAttachment
    extra = 0
    readonly_fields = ["uploaded_by", "original_name", "content_type", "size", "created_at"]


class SponsoredFilter(admin.SimpleListFilter):
    title = "sponsorship"
    parameter_name = "sponsored"

    def lookups(self, request, model_admin):
        return [("active", "Sponsored now"), ("ended", "Sponsorship ended"), ("never", "Never sponsored")]

    def queryset(self, request, queryset):
        from django.utils import timezone

        now = timezone.now()
        if self.value() == "active":
            return queryset.filter(sponsored_until__gt=now)
        if self.value() == "ended":
            return queryset.filter(sponsored_until__lte=now)
        if self.value() == "never":
            return queryset.filter(sponsored_until__isnull=True)
        return queryset


def _sponsor(days):
    def action(modeladmin, request, queryset):
        from datetime import timedelta

        from django.utils import timezone

        until = timezone.now() + timedelta(days=days)
        updated = queryset.update(sponsored_until=until)
        modeladmin.message_user(request, f"{updated} post(s) sponsored until {until:%d %b %Y}. Set the sponsor name and link on each post.")
    action.__name__ = f"sponsor_{days}_days"
    action.short_description = f"Sponsor for {days} days"
    return action


@admin.action(description="Stop sponsoring")
def stop_sponsoring(modeladmin, request, queryset):
    from django.utils import timezone

    updated = queryset.filter(sponsored_until__gt=timezone.now()).update(sponsored_until=timezone.now())
    modeladmin.message_user(request, f"Stopped sponsoring {updated} post(s).")


@admin.register(Discussion)
class DiscussionAdmin(admin.ModelAdmin):
    list_display = ["__str__", "author", "community", "created_at", "view_count", "share_count", "sponsor_status", "sponsored_impressions", "sponsored_clicks", "click_rate"]
    search_fields = ["title", "body", "author__username", "community__name", "sponsor_name"]
    list_filter = [SponsoredFilter, "category", "created_at"]
    inlines = [DiscussionAttachmentInline]
    actions = [_sponsor(7), _sponsor(30), stop_sponsoring]
    readonly_fields = ["view_count", "share_count", "sponsored_impressions", "sponsored_clicks", "repost_of"]
    fieldsets = [
        (None, {"fields": ["author", "community", "title", "body", "content_html", "category", "repost_of"]}),
        ("Sponsored post (paid promotion)", {
            "description": "Agree the price with the business and collect payment (e.g. M-Pesa), then set an end date. "
                           "The post appears in everyone's feeds labelled “Sponsored · name”, one per page.",
            "fields": ["sponsored_until", "sponsor_name", "sponsor_url", "sponsored_impressions", "sponsored_clicks"],
        }),
        ("Stats", {"fields": ["view_count", "share_count"]}),
    ]
    raw_id_fields = ["author", "community"]

    @admin.display(description="Sponsored")
    def sponsor_status(self, post):
        from django.utils import timezone

        if not post.sponsored_until:
            return "—"
        return f"until {post.sponsored_until:%d %b}" if post.sponsored_until > timezone.now() else "ended"

    @admin.display(description="Click rate")
    def click_rate(self, post):
        if not post.sponsored_impressions:
            return "—"
        return f"{post.sponsored_clicks * 100 / post.sponsored_impressions:.1f}%"


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ["discussion", "author", "parent", "created_at"]
    search_fields = ["body", "author__username", "discussion__title"]


@admin.register(DiscussionReaction)
class DiscussionReactionAdmin(admin.ModelAdmin):
    list_display = ["discussion", "user", "reaction_type", "created_at"]
    list_filter = ["reaction_type", "created_at"]


@admin.register(DiscussionBookmark)
class DiscussionBookmarkAdmin(admin.ModelAdmin):
    list_display = ["discussion", "user", "created_at"]
    search_fields = ["discussion__title", "user__username"]


@admin.register(DiscussionAttachment)
class DiscussionAttachmentAdmin(admin.ModelAdmin):
    list_display = ["original_name", "discussion", "uploaded_by", "content_type", "size", "processing", "created_at"]
    list_filter = ["processing", "content_type"]
    search_fields = ["original_name", "discussion__title", "uploaded_by__username"]


from .models import Poll, PollOption


class PollOptionInline(admin.TabularInline):
    model = PollOption
    extra = 0
    fields = ["position", "text", "vote_count"]
    readonly_fields = ["vote_count"]

    @admin.display(description="Votes")
    def vote_count(self, option):
        return option.votes.count() if option.pk else 0


@admin.register(Poll)
class PollAdmin(admin.ModelAdmin):
    list_display = ["question", "discussion", "allows_multiple", "closes_at", "created_at"]
    search_fields = ["question", "discussion__author__username"]
    raw_id_fields = ["discussion"]
    inlines = [PollOptionInline]
