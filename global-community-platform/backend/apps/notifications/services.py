import re
from functools import partial

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.db import transaction

from .models import Notification, NotificationPreference
from apps.communities.models import Community, CommunityMembership

User = get_user_model()


def _preference_field(notification_type):
    if notification_type == Notification.MESSAGE:
        return "messages_enabled"

    if notification_type == Notification.MENTION:
        return "mentions_enabled"

    if notification_type in {Notification.FOLLOW, Notification.FOLLOW_REQUEST, Notification.FOLLOW_ACCEPTED}:
        return "social_enabled"

    if notification_type in {
        Notification.DISCUSSION_COMMENT,
        Notification.DISCUSSION_REPLY,
        Notification.DISCUSSION_REACTION,
    }:
        return "discussions_enabled"

    if notification_type in {
        Notification.COMMUNITY_MEMBERSHIP_REQUEST,
        Notification.COMMUNITY_MEMBERSHIP_APPROVED,
        Notification.COMMUNITY_ANNOUNCEMENT,
        Notification.COMMUNITY_INVITATION,
        Notification.EVENT_CREATED,
        Notification.EVENT_UPDATED,
        Notification.EVENT_CANCELLED,
        Notification.EVENT_RSVP,
        Notification.EVENT_REMINDER,
    }:
        return "communities_enabled"

    return "system_enabled"

def _serialize_notification(notification):
    return {
        "id": notification.id,
        "notification_type": notification.notification_type,
        "title": notification.title,
        "body": notification.body,
        "target_url": notification.target_url,
        "data": notification.data,
        "actor": notification.actor_id,
        "actor_username": notification.actor.username if notification.actor_id else None,
        "is_read": notification.is_read,
        "read_at": notification.read_at.isoformat() if notification.read_at else None,
        "created_at": notification.created_at.isoformat(),
    }


def _broadcast_notification(notification_id, recipient_id):
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    try:
        notification = Notification.objects.select_related("actor").get(pk=notification_id)
    except Notification.DoesNotExist:
        return
    unread_count = Notification.objects.filter(recipient_id=recipient_id, is_read=False).count()
    async_to_sync(channel_layer.group_send)(
        f"notifications_user_{recipient_id}",
        {
            "type": "notification.event",
            "data": {
                "type": "notification.new",
                "notification": _serialize_notification(notification),
                "unread_count": unread_count,
            },
        },
    )


def create_notification(
    recipient,
    notification_type,
    title,
    body="",
    target_url="",
    actor=None,
    data=None,
):
    """Create and broadcast a notification. Self-notifications are ignored."""
    if recipient is None or not getattr(recipient, "is_authenticated", False):
        return None
    if actor and actor.pk == recipient.pk:
        return None
    if actor:
        from apps.safety.services import is_blocked_between

        if is_blocked_between(actor, recipient):
            return None

    preferences, _ = NotificationPreference.objects.get_or_create(user=recipient)
    if not getattr(preferences, _preference_field(notification_type), True):
        return None

    notification = Notification.objects.create(
        recipient=recipient,
        actor=actor,
        notification_type=notification_type,
        title=str(title)[:160],
        body=str(body)[:500],
        target_url=str(target_url)[:500],
        data=data or {},
    )
    transaction.on_commit(partial(_broadcast_notification, notification.id, recipient.id))
    return notification


def create_mention_notifications(text, actor, target_url="", context_label="", allowed_recipient_ids=None):
    """Notify active users mentioned as @username in a text string."""
    if not text or not actor or not getattr(actor, "is_authenticated", False):
        return []
    usernames = set(re.findall(r"(?<![A-Za-z0-9_])@([A-Za-z0-9_.-]{2,30})", str(text)))
    if not usernames:
        return []
    recipients = User.objects.filter(username__in=usernames, is_active=True).exclude(pk=actor.pk)
    if allowed_recipient_ids is not None:
        recipients = recipients.filter(pk__in=allowed_recipient_ids)
    created = []
    for recipient in recipients:
        notification = create_notification(
            recipient=recipient,
            notification_type=Notification.MENTION,
            title=f"{actor.username} mentioned you",
            body=context_label or "You were mentioned in a conversation.",
            target_url=target_url,
            actor=actor,
        )
        if notification:
            created.append(notification)
    return created


def notify_chat_message(message):
    conversation = message.conversation
    recipients = User.objects.filter(
        chat_memberships__conversation=conversation,
        chat_memberships__is_active=True,
    ).exclude(pk=message.sender_id).distinct()
    target_url = f"/messages?conversation={conversation.id}"
    for recipient in recipients:
        create_notification(
            recipient=recipient,
            notification_type=Notification.MESSAGE,
            title=f"New message from {message.sender.username}",
            body=message.body,
            target_url=target_url,
            actor=message.sender,
            data={"conversation_id": conversation.id, "message_id": message.id},
        )
    participant_ids = conversation.memberships.filter(is_active=True).values_list("user_id", flat=True)
    create_mention_notifications(
        message.body,
        message.sender,
        target_url=target_url,
        context_label=f"Mentioned you in a message in {conversation.title or 'a conversation'}.",
        allowed_recipient_ids=participant_ids,
    )



def _can_access_discussion(user, discussion):
    community = discussion.community
    if not community or community.visibility == Community.PUBLIC:
        return True
    return CommunityMembership.objects.filter(
        community=community, user=user, status=CommunityMembership.ACTIVE
    ).exists()


def notify_discussion_comment(comment):
    discussion = comment.discussion
    target_url = f"/discussions/{discussion.id}"
    notification_type = Notification.DISCUSSION_REPLY if comment.parent_id else Notification.DISCUSSION_COMMENT
    notified_user_ids = set()
    targets = [discussion.author]
    if comment.parent_id:
        targets.append(comment.parent.author)
    for recipient in targets:
        if not _can_access_discussion(recipient, discussion):
            continue
        if recipient.pk in notified_user_ids:
            continue
        notified_user_ids.add(recipient.pk)
        create_notification(
            recipient=recipient,
            notification_type=notification_type,
            title=f"{comment.author.username} replied to your comment" if comment.parent_id and recipient.pk == comment.parent.author_id else f"{comment.author.username} commented on your discussion",
            body=comment.body,
            target_url=target_url,
            actor=comment.author,
            data={"discussion_id": discussion.id, "comment_id": comment.id},
        )
    allowed_ids = None
    if discussion.community and discussion.community.visibility != Community.PUBLIC:
        allowed_ids = discussion.community.memberships.filter(
            status=CommunityMembership.ACTIVE
        ).values_list("user_id", flat=True)
    create_mention_notifications(
        comment.body,
        comment.author,
        target_url=target_url,
        context_label=f"Mentioned you in a comment on {discussion.title}.",
        allowed_recipient_ids=allowed_ids,
    )


def notify_discussion_reaction(discussion, actor, reaction_type):
    if _can_access_discussion(discussion.author, discussion):
        create_notification(
            recipient=discussion.author,
            notification_type=Notification.DISCUSSION_REACTION,
            title=f"{actor.username} reacted to your discussion",
            body=f"Reaction: {reaction_type}",
            target_url=f"/discussions/{discussion.id}",
            actor=actor,
            data={"discussion_id": discussion.id, "reaction_type": reaction_type},
        )


def notify_membership_request(community, applicant):
    managers = User.objects.filter(
        community_memberships__community=community,
        community_memberships__status="active",
        community_memberships__role__in=["owner", "admin"],
    ).distinct()
    for manager in managers:
        create_notification(
            recipient=manager,
            notification_type=Notification.COMMUNITY_MEMBERSHIP_REQUEST,
            title=f"New join request for {community.name}",
            body=f"@{applicant.username} requested to join your community.",
            target_url=f"/communities/{community.id}?tab=manage",
            actor=applicant,
            data={"community_id": community.id, "applicant_id": applicant.id},
        )


def notify_membership_approved(membership, reviewer):
    create_notification(
        recipient=membership.user,
        notification_type=Notification.COMMUNITY_MEMBERSHIP_APPROVED,
        title=f"Your request to join {membership.community.name} was approved",
        body="You are now a member of this community.",
        target_url=f"/communities/{membership.community_id}",
        actor=reviewer,
        data={"community_id": membership.community_id},
    )


def notify_community_announcement(announcement):
    members = User.objects.filter(
        community_memberships__community=announcement.community,
        community_memberships__status="active",
    ).exclude(pk=announcement.posted_by_id).distinct()
    for member in members:
        create_notification(
            recipient=member,
            notification_type=Notification.COMMUNITY_ANNOUNCEMENT,
            title=f"New announcement in {announcement.community.name}",
            body=announcement.title,
            target_url=f"/communities/{announcement.community_id}?tab=about",
            actor=announcement.posted_by,
            data={"community_id": announcement.community_id, "announcement_id": announcement.id},
        )

def _notify_event_members(event, actor, notification_type, title, body):
    members = User.objects.filter(
        community_memberships__community=event.community,
        community_memberships__status=CommunityMembership.ACTIVE,
        is_active=True,
    ).exclude(pk=actor.pk).distinct()

    for member in members:
        create_notification(
            recipient=member,
            notification_type=notification_type,
            title=title,
            body=body,
            target_url=f"/communities/{event.community_id}?tab=events",
            actor=actor,
            data={
                "event_id": event.id,
                "community_id": event.community_id,
            },
        )


def notify_event_created(event):
    _notify_event_members(
        event=event,
        actor=event.created_by,
        notification_type=Notification.EVENT_CREATED,
        title=f"New event in {event.community.name}",
        body=event.title,
    )


def notify_event_updated(event, actor):
    _notify_event_members(
        event=event,
        actor=actor,
        notification_type=Notification.EVENT_UPDATED,
        title=f"Event updated: {event.title}",
        body=f"The event in {event.community.name} has been updated.",
    )


def notify_event_cancelled(event, actor):
    _notify_event_members(
        event=event,
        actor=actor,
        notification_type=Notification.EVENT_CANCELLED,
        title=f"Event cancelled: {event.title}",
        body=f"The event in {event.community.name} has been cancelled.",
    )


def notify_event_rsvp(rsvp):
    event = rsvp.event

    create_notification(
        recipient=event.created_by,
        notification_type=Notification.EVENT_RSVP,
        title=f"{rsvp.user.username} responded to your event",
        body=f"{rsvp.user.username}: {rsvp.get_response_display()} — {event.title}",
        target_url=f"/communities/{event.community_id}?tab=events",
        actor=rsvp.user,
        data={
            "event_id": event.id,
            "community_id": event.community_id,
            "response": rsvp.response,
        },
    )


def notify_new_follower(follow):
    follower = follow.follower
    name = follower.get_full_name() or follower.username
    return create_notification(
        recipient=follow.following,
        actor=follower,
        notification_type=Notification.FOLLOW,
        title=f"{name} started following you",
        body="Tap to see their profile.",
        target_url=f"/u/{follower.username}",
        data={"username": follower.username},
    )


def notify_follow_request(follow_request):
    requester = follow_request.requester
    name = requester.get_full_name() or requester.username
    return create_notification(
        recipient=follow_request.target, actor=requester, notification_type=Notification.FOLLOW_REQUEST,
        title=f"{name} wants to follow you", body="Approve or decline in Follow requests.",
        target_url="/people/requests", data={"username": requester.username},
    )


def notify_follow_accepted(target, requester):
    name = target.get_full_name() or target.username
    return create_notification(
        recipient=requester, actor=target, notification_type=Notification.FOLLOW_ACCEPTED,
        title=f"{name} accepted your follow request", body="You can now see their posts and stories.",
        target_url=f"/u/{target.username}", data={"username": target.username},
    )
