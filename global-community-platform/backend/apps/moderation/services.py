"""Who may moderate what, what a reported thing looks like, and applying decisions."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.accounts.security import revoke_all_sessions
from apps.communities.models import CommunityMembership
from apps.notifications.models import Notification
from apps.notifications.services import create_notification
from apps.safety.models import Report

from .models import ModerationAction

User = get_user_model()
MOD_ROLES = (CommunityMembership.OWNER, CommunityMembership.ADMIN, CommunityMembership.MODERATOR)
COMMUNITY_TARGETS = (Report.POST, Report.COMMENT)
REASON_LABELS = dict(Report.REASONS)


# ---------------------------------------------------------------- permissions

def moderated_community_ids(user):
    if not user or not user.is_authenticated:
        return []
    return list(CommunityMembership.objects.filter(
        user=user, status=CommunityMembership.ACTIVE, role__in=MOD_ROLES,
    ).values_list("community_id", flat=True))


def can_moderate(user):
    return bool(user and user.is_authenticated and (user.is_staff or moderated_community_ids(user)))


def reports_in_scope(user):
    """Reports this moderator may see: everything for staff; posts/comments in their communities otherwise."""
    reports = Report.objects.all()
    if user.is_staff:
        return reports
    from apps.discussions.models import Comment, Discussion

    ids = moderated_community_ids(user)
    posts = Discussion.objects.filter(community_id__in=ids).values("pk")
    comments = Comment.objects.filter(discussion__community_id__in=ids).values("pk")
    from django.db.models import Q

    return reports.filter(Q(target_type=Report.POST, target_id__in=posts) | Q(target_type=Report.COMMENT, target_id__in=comments))


# ---------------------------------------------------------------- targets

def load_target(target_type, target_id):
    """Return (object, owner, community) for a reportable thing, or (None, None, None) if it is gone."""
    from apps.discussions.models import Comment, Discussion
    from apps.messaging.models import Message
    from apps.stories.models import Story

    if target_type == Report.POST:
        obj = Discussion.objects.select_related("author", "community").filter(pk=target_id).first()
        return (obj, obj.author, obj.community) if obj else (None, None, None)
    if target_type == Report.COMMENT:
        obj = Comment.objects.select_related("author", "discussion__community").filter(pk=target_id).first()
        return (obj, obj.author, obj.discussion.community) if obj else (None, None, None)
    if target_type == Report.STORY:
        obj = Story.objects.select_related("author").filter(pk=target_id).first()
        return (obj, obj.author, None) if obj else (None, None, None)
    if target_type == Report.MESSAGE:
        obj = Message.objects.select_related("sender").filter(pk=target_id, deleted_at__isnull=True).first()
        return (obj, obj.sender, None) if obj else (None, None, None)
    if target_type == Report.USER:
        obj = User.objects.filter(pk=target_id).first()
        return (obj, obj, None) if obj else (None, None, None)
    return None, None, None


def describe(target_type, obj, limit=400):
    """What a moderator needs to judge the thing: its text, a picture if any, and a link."""
    if obj is None:
        return {"text": "", "image": "", "url": "", "gone": True}
    if target_type == Report.POST:
        from apps.discussions.images import image_url

        media = next(iter(obj.attachments.all()), None)
        poll = getattr(obj, "poll", None) if hasattr(obj, "poll") else None
        text = "\n".join(part for part in [obj.title, obj.body, f"Poll: {poll.question}" if poll else ""] if part)
        return {"text": text[:limit], "image": image_url(media, "thumb") if media else "", "url": f"/discussions/{obj.pk}", "gone": False}
    if target_type == Report.COMMENT:
        return {"text": obj.body[:limit], "image": "", "url": f"/discussions/{obj.discussion_id}", "gone": False}
    if target_type == Report.STORY:
        return {"text": (obj.text or obj.alt_text or f"{obj.get_media_type_display()} story")[:limit], "image": "", "url": "", "gone": False}
    if target_type == Report.MESSAGE:
        return {"text": obj.body[:limit], "image": "", "url": "", "gone": False}
    profile = getattr(obj, "profile", None)
    bio = profile.bio if profile else ""
    return {"text": f"{obj.get_full_name() or obj.username}\n{bio}".strip()[:limit], "image": "", "url": f"/u/{obj.username}", "gone": False}


def remove_target(target_type, obj):
    if target_type == Report.STORY:
        obj.delete_files()
        obj.delete()
    elif target_type == Report.MESSAGE:
        obj.body = ""
        obj.deleted_at = timezone.now()
        obj.save(update_fields=["body", "deleted_at"])
    else:  # post or comment (post attachments' files are removed by a signal)
        obj.delete()


# ---------------------------------------------------------------- decisions

class ModerationError(Exception):
    pass


NOTICE = {
    ModerationAction.REMOVE: "We removed your {thing} because it goes against our community rules.",
    ModerationAction.WARN: "This is a warning about your {thing}. Repeated violations can lead to a suspension.",
}
THING = {Report.POST: "post", Report.COMMENT: "comment", Report.STORY: "story", Report.MESSAGE: "message", Report.USER: "account"}


def check_power(moderator, action, target_type, community, owner):
    if moderator.is_staff:
        if owner is not None and owner.pk == moderator.pk and action != ModerationAction.DISMISS:
            raise ModerationError("You can't take action on your own content.")
        if owner is not None and owner.is_staff and action in (ModerationAction.SUSPEND, ModerationAction.BAN) and not moderator.is_superuser:
            raise ModerationError("Only a superuser can suspend or ban staff.")
        return
    # Community moderators: dismiss or remove posts/comments in communities they moderate.
    if target_type not in COMMUNITY_TARGETS or community is None or community.pk not in moderated_community_ids(moderator):
        raise ModerationError("You don't moderate this.")
    if action not in (ModerationAction.DISMISS, ModerationAction.REMOVE):
        raise ModerationError("Only site staff can warn, suspend or ban accounts.")
    if owner is not None and owner.pk == moderator.pk:
        raise ModerationError("You can't take action on your own content.")


def apply_decision(moderator, target_type, target_id, action, reason="", days=None, remove_content=False):
    obj, owner, community = load_target(target_type, target_id)
    open_reports = Report.objects.filter(target_type=target_type, target_id=target_id, status=Report.OPEN)
    if owner is None:
        # Already deleted (by its author or another moderator): just close the reports.
        owner = open_reports.exclude(target_owner=None).values_list("target_owner", flat=True).first()
        owner = User.objects.filter(pk=owner).first() if owner else None
    if action not in dict(ModerationAction.ACTIONS) or action == ModerationAction.RESTORE:
        raise ModerationError("Unknown action.")
    check_power(moderator, action, target_type, community, owner)
    if action != ModerationAction.DISMISS and not reason.strip():
        raise ModerationError("Give a reason. The person is told why.")
    if action == ModerationAction.REMOVE and (obj is None or target_type == Report.USER):
        raise ModerationError("There's nothing to remove." if obj is None else "Accounts can't be removed; suspend or ban instead.")
    if action in (ModerationAction.WARN, ModerationAction.SUSPEND, ModerationAction.BAN) and owner is None:
        raise ModerationError("This account no longer exists.")
    if action == ModerationAction.SUSPEND and not (days and 1 <= int(days) <= 365):
        raise ModerationError("Choose a suspension of 1 to 365 days.")

    snapshot = {**describe(target_type, obj, limit=2000), "owner": owner.username if owner else ""}
    if target_type == Report.POST and obj is not None:
        snapshot["attachments"] = [a.original_name for a in obj.attachments.all()]
    until = None
    with transaction.atomic():
        removing = action == ModerationAction.REMOVE or (remove_content and action in (ModerationAction.SUSPEND, ModerationAction.BAN) and obj is not None and target_type != Report.USER)
        if removing:
            remove_target(target_type, obj)
        if action == ModerationAction.SUSPEND:
            until = timezone.now() + timedelta(days=int(days))
            UserProfile.objects.update_or_create(user=owner, defaults={"suspended_until": until, "suspension_reason": reason.strip()[:500]})
            revoke_all_sessions(owner)
        elif action == ModerationAction.BAN:
            owner.is_active = False
            owner.save(update_fields=["is_active"])
            UserProfile.objects.update_or_create(user=owner, defaults={"suspension_reason": reason.strip()[:500]})
            revoke_all_sessions(owner)
        reporters = list(open_reports.values_list("reporter_id", flat=True))
        closed = open_reports.update(
            status=Report.DISMISSED if action == ModerationAction.DISMISS else Report.ACTIONED,
            reviewed_by=moderator, reviewed_at=timezone.now(),
        )
        log = ModerationAction.objects.create(
            moderator=moderator, action=ModerationAction.REMOVE if removing and action == ModerationAction.REMOVE else action,
            target_type=target_type, target_id=target_id, target_user=owner, community=community,
            reason=reason.strip(), snapshot=snapshot, reports_closed=closed, suspended_until=until,
        )

    thing = THING.get(target_type, "content")
    if owner is not None and action in NOTICE:
        create_notification(owner, Notification.SYSTEM, "Community rules", f"{NOTICE[action].format(thing=thing)} Reason: {reason.strip()}")
    if owner is not None and removing and action != ModerationAction.REMOVE:
        create_notification(owner, Notification.SYSTEM, "Community rules", f"We removed your {thing}. Reason: {reason.strip()}")
    outcome = ("We reviewed it and didn't find a violation of our rules." if action == ModerationAction.DISMISS
               else "We took action. Thank you for helping keep CommonGround safe.")
    for reporter_id in set(reporters):
        reporter = User.objects.filter(pk=reporter_id).first()
        if reporter is not None and (owner is None or reporter_id != owner.pk):
            create_notification(reporter, Notification.SYSTEM, "Update on your report", f"You reported a {thing}. {outcome}")
    return log


def restore_account(moderator, user, reason=""):
    if not moderator.is_staff:
        raise ModerationError("Only site staff can lift suspensions and bans.")
    profile, _ = UserProfile.objects.get_or_create(user=user)
    if user.is_active and not (profile.suspended_until and profile.suspended_until > timezone.now()):
        raise ModerationError("This account isn't suspended or banned.")
    with transaction.atomic():
        user.is_active = True
        user.save(update_fields=["is_active"])
        profile.suspended_until = None
        profile.suspension_reason = ""
        profile.save(update_fields=["suspended_until", "suspension_reason"])
        return ModerationAction.objects.create(moderator=moderator, action=ModerationAction.RESTORE, target_type=Report.USER,
                                               target_id=user.pk, target_user=user, reason=reason.strip())


def active_suspension(user):
    """(until, reason) if the user is suspended right now, else None."""
    profile = UserProfile.objects.filter(user=user).values("suspended_until", "suspension_reason").first()
    if profile and profile["suspended_until"] and profile["suspended_until"] > timezone.now():
        return profile["suspended_until"], profile["suspension_reason"]
    return None
