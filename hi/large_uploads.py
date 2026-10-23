"""Bounded, retryable local-disk upload protocol with crash recovery."""
import os
import shutil
import time
from contextlib import contextmanager
from pathlib import Path
from django.conf import settings
from django.db.models import Sum, F
from django.utils import timezone
from .models import MediaUpload


class UploadBusy(Exception):
    pass


def root():
    path = Path(settings.MEDIA_UPLOAD_ROOT)
    path.mkdir(parents=True, exist_ok=True)
    return path


def partial_path(upload):
    return root() / (str(upload.pk) + '.part')


@contextmanager
def upload_lock(key):
    """O_EXCL works on Windows and Unix and across multiple server processes."""
    path = root() / (str(key) + '.lock')
    try:
        # Requests hold the lock briefly. An abandoned lock expires after a crash.
        if path.exists() and time.time() - path.stat().st_mtime > 300:
            path.unlink(missing_ok=True)
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise UploadBusy from exc
    try:
        os.close(descriptor)
        yield
    finally:
        path.unlink(missing_ok=True)


def available_bytes():
    # Staging and final files must share a volume to finalize without another copy.
    staging = root()
    destination = Path(settings.MEDIA_ROOT) / 'uploads'
    destination.mkdir(parents=True, exist_ok=True)
    if staging.stat().st_dev != destination.stat().st_dev:
        raise OSError('Staging and media must be on the same volume')
    return shutil.disk_usage(staging).free


def reserved_bytes():
    return MediaUpload.objects.filter(state='uploading', expires_at__gt=timezone.now()).aggregate(
        value=Sum(F('size') - F('offset')),
    )['value'] or 0


def has_capacity(size):
    return available_bytes() >= size + reserved_bytes() + settings.MEDIA_UPLOAD_RESERVE_BYTES


def discard_expired(limit=20):
    from .media_files import extension
    for item in MediaUpload.objects.filter(state='uploading', expires_at__lte=timezone.now())[:limit]:
        try:
            with upload_lock(item.pk):
                item.refresh_from_db()
                if item.state != 'uploading' or item.expires_at > timezone.now(): continue
                partial_path(item).unlink(missing_ok=True)
                (Path(settings.MEDIA_ROOT) / f'uploads/{item.pk}.{extension(item.name)}').unlink(missing_ok=True)
                item.state = 'cancelled'; item.save(update_fields=['state'])
        except UploadBusy:
            continue
