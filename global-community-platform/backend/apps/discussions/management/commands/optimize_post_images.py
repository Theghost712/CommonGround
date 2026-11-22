from django.core.management.base import BaseCommand

from apps.common.media import MediaRejected
from apps.discussions.images import build_variants
from apps.discussions.models import DiscussionAttachment


class Command(BaseCommand):
    help = "Create WebP display/thumbnail copies for photos uploaded before the image pipeline existed. Originals are left untouched."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        pending = DiscussionAttachment.objects.filter(display="", content_type__startswith="image/").order_by("pk")
        done = failed = 0
        for attachment in pending.iterator():
            if options["dry_run"]:
                self.stdout.write(f"would optimise #{attachment.pk} {attachment.original_name}")
                continue
            try:
                with attachment.file.open("rb") as handle:
                    display, thumb, width, height, colour = build_variants(handle)
            except (MediaRejected, FileNotFoundError, OSError) as error:
                failed += 1
                self.stderr.write(f"skip #{attachment.pk} {attachment.original_name}: {error}")
                continue
            attachment.display.save(display.name, display, save=False)
            attachment.thumbnail.save(thumb.name, thumb, save=False)
            attachment.width, attachment.height, attachment.color = width, height, colour
            attachment.save(update_fields=["display", "thumbnail", "width", "height", "color"])
            done += 1
        self.stdout.write(f"Optimised {done} photo(s); {failed} skipped.")
