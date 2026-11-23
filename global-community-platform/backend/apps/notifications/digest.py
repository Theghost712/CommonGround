"""Weekly "what you missed" email.

Sent to members who:
- have a confirmed email address (unconfirmed ones would bounce or look like spam),
- haven't opened CommonGround for INACTIVE_DAYS days,
- left the digest switched on, and haven't had one in the last 7 days,
- actually have something new (followers, messages, notifications, posts, events).

At most DIGEST_DAILY_LIMIT emails a day (Gmail allows ~500), oldest-first, so a big
member list is spread over several days. Every email has a one-click unsubscribe
link (signed; no sign-in needed) and a List-Unsubscribe header.
"""

import logging
from datetime import timedelta
from html import escape

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.db.models import Count, Q
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)
User = get_user_model()
INACTIVE_DAYS = 3
_signer = signing.TimestampSigner(salt="digest-unsubscribe")


def site_link(path):
    return settings.FRONTEND_URL.rstrip("/") + path


def unsubscribe_link(user):
    return site_link(f"/api/v1/notifications/digest/unsubscribe/?t={_signer.sign(str(user.pk))}")


def last_active(user):
    from apps.messaging.models import UserPresence

    times = [user.last_login, user.date_joined]
    presence = UserPresence.objects.filter(user=user).values("is_online", "last_seen").first()
    if presence:
        if presence["is_online"]:
            return timezone.now()
        times.append(presence["last_seen"])
    return max(t for t in times if t)


def collect(user, since):
    """What happened for `user` since `since`. Returns a dict (empty lists when nothing)."""
    from apps.discussions.views import visible_discussions, with_stats
    from apps.events.models import CommunityEvent
    from apps.messaging.models import ConversationMember, Message
    from apps.social.models import Follow

    from .models import Notification

    followers = list(Follow.objects.filter(following=user, created_at__gte=since).select_related("follower").order_by("-created_at")[:5])
    follower_total = Follow.objects.filter(following=user, created_at__gte=since).count()

    unread_messages = 0
    for member in ConversationMember.objects.filter(user=user, is_active=True):
        qs = Message.objects.filter(conversation_id=member.conversation_id, deleted_at__isnull=True).exclude(sender=user).exclude(kind="system")
        if member.last_read_at:
            qs = qs.filter(created_at__gt=member.last_read_at)
        unread_messages += qs.filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())).count()

    unread_notifications = Notification.objects.filter(recipient=user, is_read=False, created_at__gte=since).exclude(notification_type=Notification.MESSAGE).count()

    followed = Follow.objects.filter(follower=user).values("following_id")
    top_posts = list(with_stats(visible_discussions(user), user).filter(author_id__in=followed, created_at__gte=since)
                     .select_related("author").order_by("-reactions_total", "-comments_total", "-created_at")[:3])

    events = list(CommunityEvent.objects.filter(
        status=CommunityEvent.SCHEDULED, starts_at__gte=timezone.now(), starts_at__lte=timezone.now() + timedelta(days=7),
        community__memberships__user=user, community__memberships__status="active",
    ).select_related("community").order_by("starts_at").distinct()[:3])

    return {"followers": followers, "follower_total": follower_total, "unread_messages": unread_messages,
            "unread_notifications": unread_notifications, "top_posts": top_posts, "events": events}


def has_news(data):
    return bool(data["follower_total"] or data["unread_messages"] or data["unread_notifications"] or data["top_posts"] or data["events"])


def render(user, data):
    """(subject, text, html) for one member."""
    home = site_link("/home")
    name = user.first_name or user.username
    lines, blocks = [], []
    headline = []
    if data["follower_total"]:
        headline.append(f"{data['follower_total']} new follower{'s' if data['follower_total'] != 1 else ''}")
    if data["unread_messages"]:
        headline.append(f"{data['unread_messages']} unread message{'s' if data['unread_messages'] != 1 else ''}")
    if data["unread_notifications"]:
        headline.append(f"{data['unread_notifications']} notification{'s' if data['unread_notifications'] != 1 else ''}")
    subject = f"{name}, you have {headline[0]}" if headline else f"{name}, here's what's new on CommonGround"

    def section(title, items):
        lines.append(f"\n{title}")
        lines.extend(f"- {text} ({url})" for text, url in items)
        rows = "".join(f'<li style="margin:0 0 8px"><a href="{escape(url)}" style="color:#4f46e5;text-decoration:none">{escape(text)}</a></li>' for text, url in items)
        blocks.append(f'<h2 style="font-size:16px;margin:22px 0 8px;color:#101828">{escape(title)}</h2><ul style="padding-left:18px;margin:0">{rows}</ul>')

    if headline:
        lines.append("You have " + ", ".join(headline) + ".")
        blocks.append(f'<p style="font-size:15px;color:#344054;margin:0 0 6px">You have <strong>{escape(", ".join(headline))}</strong>.</p>')
    if data["followers"]:
        section("New followers", [(f"@{f.follower.username} started following you", site_link(f"/u/{f.follower.username}")) for f in data["followers"]])
    if data["unread_messages"]:
        section("Messages", [(f"Read your {data['unread_messages']} unread message{'s' if data['unread_messages'] != 1 else ''}", site_link("/messages"))])
    if data["top_posts"]:
        section("Popular from people you follow", [(f"@{p.author.username}: {(p.title or p.body or 'a new photo or video')[:90]}", site_link(f"/discussions/{p.pk}")) for p in data["top_posts"]])
    if data["events"]:
        section("Coming up this week", [(f"{e.title} · {timezone.localtime(e.starts_at):%a %d %b, %H:%M} · {e.community.name}", site_link(f"/communities/{e.community_id}?tab=events")) for e in data["events"]])

    unsubscribe = unsubscribe_link(user)
    text = f"Hi {name},\n" + "\n".join(lines) + f"\n\nOpen CommonGround: {home}\n\nDon't want these weekly emails? Unsubscribe: {unsubscribe}\n"
    html = f"""<!doctype html><html><body style="margin:0;background:#f5f6f8;font-family:Arial,Helvetica,sans-serif">
<div style="max-width:560px;margin:0 auto;padding:24px 16px">
  <div style="background:#fff;border:1px solid #e4e7ec;border-radius:12px;padding:24px">
    <p style="margin:0 0 4px;font-size:13px;color:#667085">CommonGround · your week</p>
    <h1 style="font-size:20px;margin:0 0 14px;color:#101828">Hi {escape(name)}, here's what you missed</h1>
    {''.join(blocks)}
    <p style="margin:26px 0 0"><a href="{escape(home)}" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:11px 18px;border-radius:8px;font-weight:bold">Open CommonGround</a></p>
  </div>
  <p style="font-size:12px;color:#98a2b3;text-align:center;margin:14px 0 0">You get this weekly summary when you haven't visited for a few days.
  <a href="{escape(unsubscribe)}" style="color:#667085">Unsubscribe</a></p>
</div></body></html>"""
    return subject, text, html


def send_digest(user, data=None):
    data = data or collect(user, timezone.now() - timedelta(days=7))
    subject, text, html = render(user, data)
    message = EmailMultiAlternatives(subject, text, settings.DEFAULT_FROM_EMAIL, [user.email],
                                     headers={"List-Unsubscribe": f"<{unsubscribe_link(user)}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"})
    message.attach_alternative(html, "text/html")
    message.send(fail_silently=False)


def send_weekly_digests(limit=None):
    """Called daily by the scheduler. Returns how many emails were sent."""
    from .models import NotificationPreference

    limit = limit or int(getattr(settings, "DIGEST_DAILY_LIMIT", 200))
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    candidates = (User.objects.filter(is_active=True, profile__email_verified_at__isnull=False).exclude(email="")
                  .exclude(notification_preferences__email_digest_enabled=False)
                  .exclude(notification_preferences__digest_sent_at__gt=week_ago)
                  .order_by("notification_preferences__digest_sent_at", "pk"))
    sent = 0
    for user in candidates.iterator():
        if sent >= limit:
            break
        if last_active(user) > now - timedelta(days=INACTIVE_DAYS):
            continue
        data = collect(user, max(week_ago, last_active(user)))
        if not has_news(data):
            continue
        try:
            send_digest(user, data)
        except Exception:
            logger.exception("Weekly digest to user %s failed", user.pk)
            continue
        NotificationPreference.objects.update_or_create(user=user, defaults={"digest_sent_at": now})
        sent += 1
    return sent


@csrf_exempt
@require_http_methods(["GET", "POST"])
def unsubscribe_view(request):
    """One click (GET from the email link, POST from mail apps' unsubscribe button)."""
    from .models import NotificationPreference

    try:
        user_id = int(_signer.unsign(request.GET.get("t", ""), max_age=90 * 86400))
    except (signing.BadSignature, ValueError):
        return HttpResponse("<p>This unsubscribe link is invalid or too old. You can turn the weekly email off in Settings → Notifications.</p>", status=400)
    NotificationPreference.objects.update_or_create(user_id=user_id, defaults={"email_digest_enabled": False})
    return HttpResponse("""<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1">
<div style="font-family:Arial,sans-serif;max-width:480px;margin:60px auto;padding:0 16px;text-align:center">
<h1 style="font-size:20px">You're unsubscribed</h1><p>You won't get the weekly CommonGround email any more.
You can turn it back on in Settings → Notifications.</p><p><a href="/home">Back to CommonGround</a></p></div>""")
