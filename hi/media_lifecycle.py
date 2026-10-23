"""Remove only unreferenced, application-owned upload data after DB commit."""
import uuid
from pathlib import PurePosixPath
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Q
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver
from .models import MediaContent, MediaUpload
from .media_files import extension


def owned_movie(name):
    path = PurePosixPath(name)
    if path.parent != PurePosixPath('uploads'):
        return False
    try:
        identifier = uuid.UUID(path.stem)
    except ValueError:
        return False
    upload = MediaUpload.objects.filter(pk=identifier, state='completed').first()
    return bool(upload and name == f'uploads/{upload.pk}.{extension(upload.name)}')


def remove_unused(names):
    for name in set(filter(None, names)):
        # Pre-existing loose files may be intended for later CSV import. Do not prune them.
        if not (name.startswith('posters/') or owned_movie(name)):
            continue
        if not MediaContent.objects.filter(Q(image=name) | Q(poster=name)).exists():
            default_storage.delete(name)


@receiver(post_delete, sender=MediaContent)
def release_deleted_media(sender, instance, **kwargs):
    names = [instance.image.name, instance.poster.name]
    transaction.on_commit(lambda: remove_unused(names), robust=True)


@receiver(pre_save, sender=MediaContent)
def release_replaced_media(sender, instance, update_fields=None, **kwargs):
    if not instance.pk or (update_fields is not None and not {'image', 'poster'}.intersection(update_fields)):
        return
    previous = sender.objects.filter(pk=instance.pk).values('image', 'poster').first()
    if not previous:
        return
    names = [previous[field] for field in ('image', 'poster') if previous[field] != getattr(instance, field).name]
    if names:
        transaction.on_commit(lambda: remove_unused(names), robust=True)
