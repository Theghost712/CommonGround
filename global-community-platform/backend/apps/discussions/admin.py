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
    list_display = ["original_name", "discussion", "uploaded_by", "size", "created_at"]
    search_fields = ["original_name", "discussion__title", "uploaded_by__username"]
