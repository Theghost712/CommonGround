"""Block/mute lookups used by feeds, search, stories, messaging and profiles.

These run on almost every request, so each person's sets are cached (Redis in
production) and invalidated by signals the moment a block or mute changes.
"""
from django.core.cache import cache
from django.db.models import Q
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Block, Mute

CACHE_SECONDS = 10 * 60


def _key(kind, user_id):
    return f"safety:{kind}:{user_id}"


def blocked_user_ids(user):
    """Everyone `user` must not see: people they blocked and people who blocked them."""
    if user is None or not user.is_authenticated:
        return set()
    key = _key("blocked", user.pk)
    cached = cache.get(key)
    if cached is not None:
        return cached
    rows = Block.objects.filter(Q(blocker=user) | Q(blocked=user)).values_list("blocker_id", "blocked_id")
    result = {other for pair in rows for other in pair if other != user.pk}
    cache.set(key, result, CACHE_SECONDS)
    return result


def is_blocked_between(a, b):
    return b.pk in blocked_user_ids(a)


def _muted(user, field):
    if user is None or not user.is_authenticated:
        return set()
    key = _key(f"muted-{field}", user.pk)
    cached = cache.get(key)
    if cached is None:
        cached = set(Mute.objects.filter(owner=user, **{field: True}).values_list("muted_id", flat=True))
        cache.set(key, cached, CACHE_SECONDS)
    return cached


def muted_post_authors(user):
    return _muted(user, "mute_posts")


def muted_story_authors(user):
    return _muted(user, "mute_stories")


@receiver([post_save, post_delete], sender=Block, dispatch_uid="safety_block_cache")
def _forget_blocks(sender, instance, **kwargs):
    cache.delete_many([_key("blocked", instance.blocker_id), _key("blocked", instance.blocked_id)])


@receiver([post_save, post_delete], sender=Mute, dispatch_uid="safety_mute_cache")
def _forget_mutes(sender, instance, **kwargs):
    cache.delete_many([_key("muted-mute_posts", instance.owner_id), _key("muted-mute_stories", instance.owner_id)])
