"""Invites: a member shares a personal link (…/register?invite=<username>); whoever
joins through it is connected to them straight away, like WhatsApp or Facebook."""
import logging

from django.contrib.auth import get_user_model

from .services import follow_user

logger = logging.getLogger(__name__)
User = get_user_model()


def welcome_invited_user(new_user, inviter_username):
    """Connect a new member with the person who invited them. Never blocks sign-up."""
    inviter = User.objects.filter(username__iexact=inviter_username, is_active=True).exclude(pk=new_user.pk).first()
    if inviter is None:
        return None
    try:
        from apps.monetization.services import record_referral

        record_referral(inviter, new_user)  # the inviter earns ad credit once this member confirms their email
        follow_user(new_user, inviter)   # a follow request if the inviter is private
        follow_user(inviter, new_user)
        from apps.notifications.models import Notification
        from apps.notifications.services import create_notification

        name = new_user.get_full_name() or new_user.username
        create_notification(
            inviter, Notification.SYSTEM, f"{name} joined CommonGround from your invite",
            "You now follow each other.", target_url=f"/u/{new_user.username}", actor=new_user,
            data={"username": new_user.username, "invite": True},
        )
    except Exception:  # a sign-up must never fail because of the welcome extras
        logger.exception("Could not connect invited user %s with %s", new_user.pk, inviter.pk)
    return inviter
