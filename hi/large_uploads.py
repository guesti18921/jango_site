"""Bounded, retryable local-disk upload protocol with crash recovery."""
import os
import shutil
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


def final_path(upload):
    from .media_files import extension
    return Path(settings.MEDIA_ROOT) / f'uploads/{upload.pk}.{extension(upload.name)}'


@contextmanager
def upload_lock(key):
    """OS locks release on process exit; no stale-timeout or unlink races."""
    import errno
    path = root() / (str(key) + '.lock')
    file = path.open('a+b')
    try:
        if os.name == 'nt':
            import msvcrt
            if os.fstat(file.fileno()).st_size == 0:
                file.write(b'0')
                file.flush()
            file.seek(0)
            try:
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise UploadBusy from exc
                raise
        else:
            import fcntl
            try:
                fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise UploadBusy from exc
        try:
            yield
        finally:
            if os.name == 'nt':
                file.seek(0)
                msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(file.fileno(), fcntl.LOCK_UN)
    finally:
        file.close()


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
    for item in MediaUpload.objects.filter(state='uploading', expires_at__lte=timezone.now())[:limit]:
        try:
            with upload_lock(item.pk):
                item.refresh_from_db()
                if item.state != 'uploading' or item.expires_at > timezone.now(): continue
                partial_path(item).unlink(missing_ok=True)
                final_path(item).unlink(missing_ok=True)
                item.state = 'cancelled'; item.save(update_fields=['state'])
        except UploadBusy:
            continue
