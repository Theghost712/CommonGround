"""Who may see which stories, and short-lived signed links for story media."""
import hashlib
from django.core import signing
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.social.models import Follow

from .models import CloseFriend, Story, StoryHiddenFrom

MEDIA_LINK_SECONDS = 60 * 60
_signer = signing.TimestampSigner(salt="commonground.story-media")


def visible_stories(viewer):
    """Active stories `viewer` may watch: their own, plus people they follow who have not
    hidden stories from them (close-friends stories only if they are on that list)."""
    followed = Follow.objects.filter(follower=viewer).values("following_id")
    hidden_by = StoryHiddenFrom.objects.filter(hidden_user=viewer).values("owner_id")
    close_to = CloseFriend.objects.filter(friend=viewer).values("owner_id")
    others = (
        Q(author_id__in=followed)
        & ~Q(author_id__in=hidden_by)
        & (Q(audience=Story.FOLLOWERS) | Q(author_id__in=close_to))
    )
    from apps.safety.services import blocked_user_ids

    return Story.objects.filter(expires_at__gt=timezone.now()).filter(Q(author=viewer) | others).exclude(author_id__in=blocked_user_ids(viewer))


def can_view(viewer, story):
    return visible_stories(viewer).filter(pk=story.pk).exists()


def media_url(request, story, viewer, kind="media"):
    """A link that works without the JWT (so <img>/<video> can load it) for one hour."""
    if not (story.media if kind == "media" else story.thumbnail):
        return ""
    token = _signer.sign(f"{story.pk}:{viewer.pk}:{kind}")
    path = reverse("story_media", args=[story.pk])
    field = story.media if kind == "media" else story.thumbnail
    version = hashlib.sha1(field.name.encode()).hexdigest()[:10]  # changes when a video is converted
    return f"{path}?t={token}&v={version}"


def check_media_token(story_id, token):
    """Return the media kind if the token is valid for this story, else None."""
    try:
        value = _signer.unsign(token, max_age=MEDIA_LINK_SECONDS)
    except signing.BadSignature:
        return None
    story_pk, _, rest = value.partition(":")
    _viewer, _, kind = rest.partition(":")
    if story_pk != str(story_id) or kind not in {"media", "thumb"}:
        return None
    return kind
