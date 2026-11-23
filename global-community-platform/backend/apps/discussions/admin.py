from django.contrib import admin
from .models import Comment, Discussion, DiscussionAttachment, DiscussionBookmark, DiscussionReaction


class DiscussionAttachmentInline(admin.TabularInline):
    model = DiscussionAttachment
    extra = 0
    readonly_fields = ["uploaded_by", "original_name", "content_type", "size", "created_at"]


@admin.register(Discussion)
class DiscussionAdmin(admin.ModelAdmin):
    list_display = ["title", "author", "community", "category", "created_at"]
    search_fields = ["title", "body", "author__username", "community__name"]
    list_filter = ["category", "created_at"]
    inlines = [DiscussionAttachmentInline]


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
