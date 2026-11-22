"""#hashtag extraction and syncing (any language; at least one letter; 2–50 chars)."""
import re

from django.db.models.signals import post_save
from django.dispatch import receiver

HASHTAG_RE = re.compile(r"(?<![\w#&])#((?=\w*[^\W\d_])\w{2,50})", re.UNICODE)
MAX_TAGS_PER_POST = 30


def extract_hashtags(*texts):
    seen = []
    for text in texts:
        for match in HASHTAG_RE.finditer(text or ""):
            tag = match.group(1).lower()
            if tag not in seen:
                seen.append(tag)
    return seen[:MAX_TAGS_PER_POST]


def sync_hashtags(discussion):
    from .models import Hashtag

    names = extract_hashtags(discussion.title, discussion.body)
    existing = {tag.name: tag for tag in Hashtag.objects.filter(name__in=names)}
    missing = [Hashtag(name=name) for name in names if name not in existing]
    if missing:
        Hashtag.objects.bulk_create(missing, ignore_conflicts=True)
        existing = {tag.name: tag for tag in Hashtag.objects.filter(name__in=names)}
    discussion.hashtags.set(existing.values())


@receiver(post_save, sender="discussions.Discussion", dispatch_uid="sync_discussion_hashtags")
def _sync_on_save(sender, instance, **kwargs):
    sync_hashtags(instance)
