"""Permanently delete an account and everything that belongs only to it.

Things other people rely on are handed over instead of destroyed:
- a community you created passes to its longest-standing admin, moderator or
  member (and is deleted only if nobody else is in it); your events there pass
  to the new owner;
- a group chat you created passes to another member (deleted only when empty);
- direct chats stay for the other person (your messages go).

Your posts, comments, stories, messages, reactions, follows and announcements
are deleted, and so are their uploaded files (after the database commit).
"""

import logging

from django.db import transaction
from django.db.models import Case, IntegerField, Value, When

logger = logging.getLogger(__name__)


def _hand_over_communities(user):
    from apps.communities.models import Community, CommunityMembership
    from apps.events.models import CommunityEvent

    rank = Case(
        When(role=CommunityMembership.OWNER, then=Value(0)), When(role=CommunityMembership.ADMIN, then=Value(1)),
        When(role=CommunityMembership.MODERATOR, then=Value(2)), default=Value(3), output_field=IntegerField(),
    )
    for community in Community.objects.filter(created_by=user):
        heir = (CommunityMembership.objects.filter(community=community, status=CommunityMembership.ACTIVE, user__is_active=True)
                .exclude(user=user).annotate(rank=rank).order_by("rank", "joined_at", "id").first())
        if heir is None:
            community.delete()
            continue
        community.created_by_id = heir.user_id
        community.save(update_fields=["created_by"])
        heir.role = CommunityMembership.OWNER
        heir.save(update_fields=["role"])
        CommunityEvent.objects.filter(community=community, created_by=user).update(created_by=heir.user)
    # Events the user created in communities owned by others go to that community's owner.
    for event in CommunityEvent.objects.filter(created_by=user).select_related("community"):
        event.created_by_id = event.community.created_by_id
        event.save(update_fields=["created_by"])


def _hand_over_chats(user):
    from apps.messaging.models import Conversation, ConversationMember

    for conversation in Conversation.objects.filter(created_by=user):
        heir = (ConversationMember.objects.filter(conversation=conversation, is_active=True)
                .exclude(user=user).order_by("joined_at", "id").first())
        if heir is None:
            conversation.delete()
            continue
        conversation.created_by_id = heir.user_id
        conversation.save(update_fields=["created_by"])
        if conversation.conversation_type == Conversation.GROUP:
            heir.role = ConversationMember.OWNER
            heir.save(update_fields=["role"])


def _files_owned_by(user):
    """(storage, name) pairs of every uploaded file that goes away with the account."""
    from apps.discussions.models import DiscussionAttachment
    from apps.stories.models import Story

    files = []
    attachments = DiscussionAttachment.objects.filter(discussion__author=user) | DiscussionAttachment.objects.filter(uploaded_by=user)
    for attachment in attachments.distinct():
        files += [(f.storage, f.name) for f in (attachment.file, attachment.display, attachment.thumbnail) if f]
    from apps.messaging.models import Message

    for message in Message.objects.filter(sender=user).exclude(media="", thumbnail=""):
        files += [(f.storage, f.name) for f in (message.media, message.thumbnail) if f]
    for story in Story.objects.filter(author=user):
        files += [(f.storage, f.name) for f in (story.media, story.thumbnail) if f]
    return list(dict.fromkeys(files))


def delete_account(user):
    from apps.accounts.security import revoke_all_sessions
    from apps.calls.group import leave
    from apps.calls.models import GroupCall

    for call in GroupCall.objects.filter(status=GroupCall.LIVE, participants__user=user, participants__left_at__isnull=True).distinct():
        leave(call, user)
    files = _files_owned_by(user)
    with transaction.atomic():
        revoke_all_sessions(user)
        _hand_over_communities(user)
        _hand_over_chats(user)
        from apps.communities.models import CommunityAnnouncement

        CommunityAnnouncement.objects.filter(posted_by=user).delete()
        user.delete()

    def remove_files():
        for storage, name in files:
            try:
                storage.delete(name)
            except Exception:
                logger.warning("Couldn't delete %s after account deletion", name)

    transaction.on_commit(remove_files)
