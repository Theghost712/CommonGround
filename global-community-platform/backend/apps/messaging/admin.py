from django.contrib import admin
from .models import Conversation, ConversationMember, Message, MessageReadReceipt


class ConversationMemberInline(admin.TabularInline):
    model = ConversationMember
    extra = 0


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ["id", "conversation_type", "title", "created_by", "updated_at"]
    list_filter = ["conversation_type", "created_at"]
    search_fields = ["title", "created_by__username"]
    inlines = [ConversationMemberInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ["id", "conversation", "sender", "created_at", "edited_at", "deleted_at"]
    search_fields = ["body", "sender__username", "conversation__title"]
    list_filter = ["created_at", "deleted_at"]
    readonly_fields = ["created_at", "edited_at"]


admin.site.register(ConversationMember)
admin.site.register(MessageReadReceipt)
