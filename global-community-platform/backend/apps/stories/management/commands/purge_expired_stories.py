from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.stories.models import Story


class Command(BaseCommand):
    help = "Permanently delete expired stories and their media files (they vanish after 24 hours)."

    def add_arguments(self, parser):
        parser.add_argument("--batch", type=int, default=500)

    def handle(self, *args, **options):
        removed = 0
        while True:
            batch = list(Story.objects.filter(expires_at__lte=timezone.now()).order_by("pk")[: options["batch"]])
            if not batch:
                break
            for story in batch:
                story.delete_files()
            Story.objects.filter(pk__in=[s.pk for s in batch]).delete()
            removed += len(batch)
        self.stdout.write(f"Purged {removed} expired stories.")
