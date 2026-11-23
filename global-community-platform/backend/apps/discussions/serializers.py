import bleach
from rest_framework import serializers
from django.urls import reverse
from apps.communities.models import Community, CommunityMembership
from .models import Comment, Discussion, DiscussionAttachment, DiscussionReaction

ALLOWED_HTML_TAGS = set(bleach.sanitizer.ALLOWED_TAGS).union({
    "p", "br", "h1", "h2", "h3", "ul", "ol", "li", "strong", "em",
    "u", "s", "blockquote", "pre", "code", "hr",
})
ALLOWED_HTML_ATTRIBUTES = {"a": ["href", "title", "rel"], "code": ["class"]}


class DiscussionAttachmentSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    is_image = serializers.BooleanField(read_only=True)
    display_url = serializers.SerializerMethodField()
    thumb_url = serializers.SerializerMethodField()
    video_url = serializers.SerializerMethodField()
    is_video = serializers.SerializerMethodField()

    class Meta:
        model = DiscussionAttachment
        fields = ["id", "original_name", "content_type", "size", "url", "is_image", "is_video", "display_url", "thumb_url", "video_url", "duration_ms", "width", "height", "color", "alt_text", "processing", "created_at"]

    def get_is_video(self, obj):
        return (obj.content_type or "").startswith("video/")

    def get_video_url(self, obj):
        from .images import video_url

        return video_url(obj)

    def get_display_url(self, obj):
        from .images import image_url

        return image_url(obj, "display")

    def get_thumb_url(self, obj):
        from .images import image_url

        return image_url(obj, "thumb")
        read_only_fields = fields

    def get_url(self, obj):
        request = self.context.get("request")
        url = reverse("discussion_attachment_download", args=[obj.pk])
        return request.build_absolute_uri(url) if request else url


class DiscussionSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source="author.username", read_only=True)
    author_display_name = serializers.SerializerMethodField()
    author_avatar_url = serializers.SerializerMethodField()
    community_name = serializers.CharField(source="community.name", read_only=True, allow_null=True)
    comments_count = serializers.SerializerMethodField()
    reactions_count = serializers.SerializerMethodField()
    bookmarks_count = serializers.SerializerMethodField()
    has_reacted = serializers.SerializerMethodField()
    my_reaction = serializers.SerializerMethodField()
    has_bookmarked = serializers.SerializerMethodField()
    attachments = DiscussionAttachmentSerializer(many=True, read_only=True)
    poll = serializers.SerializerMethodField()
    repost_of = serializers.SerializerMethodField()
    sponsored = serializers.SerializerMethodField()

    class Meta:
        model = Discussion
        fields = ["poll", "repost_of", "sponsored", "share_count", "view_count", "id", "community", "community_name", "author", "author_username", "author_display_name", "author_avatar_url", "title", "body", "content_html", "category", "comments_count", "reactions_count", "bookmarks_count", "has_reacted", "my_reaction", "has_bookmarked", "attachments", "created_at", "updated_at"]
        read_only_fields = ["id", "author", "created_at", "updated_at", "share_count", "view_count"]

    def get_repost_of(self, obj):
        original = obj.repost_of if obj.repost_of_id else None
        if original is None:
            return None
        return DiscussionSerializer(original, context=self.context).data

    def get_sponsored(self, obj):
        from django.utils import timezone

        if obj.sponsored_until and obj.sponsored_until > timezone.now():
            return {"name": obj.sponsor_name or obj.author.get_full_name() or obj.author.username, "has_link": bool(obj.sponsor_url)}
        return None

    def get_poll(self, obj):
        from .polls import poll_data

        return poll_data(obj, self.context["request"].user)

    def get_author_display_name(self, obj):
        return obj.author.get_full_name() or obj.author.username

    def get_author_avatar_url(self, obj):
        profile = getattr(obj.author, "profile", None)
        return profile.avatar_url if profile else ""

    # Counts come from with_stats() annotations; the fallbacks cover freshly created objects.
    def get_comments_count(self, obj):
        value = getattr(obj, "comments_total", None)
        return value if value is not None else obj.comments.count()

    def get_reactions_count(self, obj):
        value = getattr(obj, "reactions_total", None)
        return value if value is not None else obj.reactions.count()

    def get_bookmarks_count(self, obj):
        value = getattr(obj, "bookmarks_total", None)
        return value if value is not None else obj.bookmarks.count()

    def get_has_reacted(self, obj):
        return self.get_my_reaction(obj) is not None

    def get_my_reaction(self, obj):
        user = self.context["request"].user
        if not user.is_authenticated:
            return None
        if hasattr(obj, "my_reaction_type"):
            return obj.my_reaction_type
        return obj.reactions.filter(user=user).values_list("reaction_type", flat=True).first()

    def get_has_bookmarked(self, obj):
        user = self.context["request"].user
        if not user.is_authenticated:
            return False
        if hasattr(obj, "my_bookmark"):
            return bool(obj.my_bookmark)
        return obj.bookmarks.filter(user=user).exists()

    def validate_community(self, community):
        if community and community.approval_status != Community.APPROVED:
            raise serializers.ValidationError("This community is not approved for discussions.")
        if community and community.visibility != Community.PUBLIC:
            user = self.context["request"].user
            if not user.is_authenticated or not CommunityMembership.objects.filter(community=community, user=user, status=CommunityMembership.ACTIVE).exists():
                raise serializers.ValidationError("You must be an active member of this community to post.")
        return community

    def validate(self, attrs):
        attrs = super().validate(attrs)
        # Regular discussions need a title and some text; photo posts (allow_untitled) don't.
        if self.instance is None and not self.context.get("allow_untitled"):
            if not str(attrs.get("title", "")).strip():
                raise serializers.ValidationError({"title": "Give your discussion a title."})
            if not str(attrs.get("body", "")).strip():
                raise serializers.ValidationError({"body": "Write something for your discussion."})
        return attrs

    def validate_content_html(self, value):
        return bleach.clean(value or "", tags=ALLOWED_HTML_TAGS, attributes=ALLOWED_HTML_ATTRIBUTES, protocols={"http", "https", "mailto"}, strip=True)


class CommentSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source="author.username", read_only=True)
    replies_count = serializers.IntegerField(source="replies.count", read_only=True)
    replies = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = ["id", "discussion", "author", "author_username", "parent", "body", "replies_count", "replies", "created_at", "updated_at"]
        read_only_fields = ["id", "author", "created_at", "updated_at"]

    def get_replies(self, obj):
        depth = self.context.get("reply_depth", 0)
        if depth >= 3:
            return []
        children = obj.replies.select_related("author").exclude(author_id__in=self.context.get("blocked_ids") or ())
        return CommentSerializer(children, many=True, context={**self.context, "reply_depth": depth + 1}).data

    def validate(self, attrs):
        if self.instance is not None:
            # Editing a comment only changes its text; it can never be moved to
            # another discussion or re-parented under a different comment.
            attrs.pop("discussion", None)
            attrs.pop("parent", None)
        parent = attrs.get("parent")
        request = self.context.get("request")
        if parent is not None and request is not None and request.user.is_authenticated:
            from apps.safety.services import is_blocked_between

            if is_blocked_between(request.user, parent.author):
                raise serializers.ValidationError({"parent": "You can't reply to this comment."})
        discussion = attrs.get("discussion") or (self.instance.discussion if self.instance else None)
        if parent and discussion and parent.discussion_id != discussion.id:
            raise serializers.ValidationError({"parent": "The parent comment must belong to the same discussion."})
        if discussion and discussion.community and discussion.community.approval_status != Community.APPROVED:
            raise serializers.ValidationError({"discussion": "This community is not approved for discussions."})
        if discussion and discussion.community and discussion.community.visibility != Community.PUBLIC:
            user = getattr(self.context.get("request"), "user", None)
            allowed = bool(user and user.is_authenticated and CommunityMembership.objects.filter(community=discussion.community, user=user, status=CommunityMembership.ACTIVE).exists())
            if not allowed:
                raise serializers.ValidationError({"discussion": "You must be an active community member to comment here."})
        return attrs
