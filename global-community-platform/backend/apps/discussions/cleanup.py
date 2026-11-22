"""Delete a post attachment's files when its row is deleted (post deleted, moderation removal).

Without this, deleting a post left its photos/videos on disk forever.
Files are removed only after the transaction commits, so a rollback keeps them.
"""
from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import DiscussionAttachment


@receiver(post_delete, sender=DiscussionAttachment, dispatch_uid="discussion_attachment_files")
def delete_attachment_files(sender, instance, **kwargs):
    fields = [instance.file, instance.display, instance.thumbnail]
    names = {(field.storage, field.name) for field in fields if field and field.name}

    def remove():
        for storage, name in names:
            try:
                storage.delete(name)
            except OSError:
                pass

    transaction.on_commit(remove)
