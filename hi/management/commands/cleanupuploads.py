from django.core.management.base import BaseCommand
from django.utils import timezone
from hi.large_uploads import partial_path, upload_lock, UploadBusy, final_path
from hi.models import MediaUpload


class Command(BaseCommand):
    help = 'Remove expired/cancelled upload data without touching published posts or connected movies.'

    def handle(self, *args, **options):
        count = 0
        for item in MediaUpload.objects.filter(expires_at__lte=timezone.now()).exclude(state='completed').iterator():
            try:
                with upload_lock(item.pk):
                    item.refresh_from_db()
                    if item.state=='completed' or item.expires_at>timezone.now(): continue
                    partial_path(item).unlink(missing_ok=True)
                    final_path(item).unlink(missing_ok=True)
                    item.state='cancelled'; item.save(update_fields=['state']); count+=1
            except UploadBusy: continue
        self.stdout.write(f'Cleaned {count} expired uploads.')
