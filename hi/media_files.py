"""Shared media types; the legacy image column also stores audio/video files."""
from pathlib import PurePosixPath
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.conf import settings

IMAGE_EXTENSIONS = ('jpg', 'jpeg', 'png', 'gif', 'webp', 'avif', 'bmp', 'tif', 'tiff', 'heic', 'heif', 'apng')
VIDEO_EXTENSIONS = ('mp4', 'm4v', 'webm', 'mov', 'mkv', 'avi', 'ogv', 'mpeg', 'mpg', '3gp')
AUDIO_EXTENSIONS = ('mp3', 'wav', 'ogg', 'oga', 'opus', 'm4a', 'aac', 'flac', 'weba', 'wma', 'aiff', 'aif')
EXTENSIONS = IMAGE_EXTENSIONS + VIDEO_EXTENSIONS + AUDIO_EXTENSIONS
MIME_TYPES = dict(zip(
    ('jpg','jpeg','png','gif','webp','avif','bmp','apng','mp4','m4v','webm','mov','ogv','mp3','wav','ogg','oga','opus','m4a','aac','flac','weba'),
    ('image/jpeg','image/jpeg','image/png','image/gif','image/webp','image/avif','image/bmp','image/png','video/mp4','video/mp4','video/webm','video/quicktime','video/ogg','audio/mpeg','audio/wav','audio/ogg','audio/ogg','audio/ogg','audio/mp4','audio/aac','audio/flac','audio/webm')))

def extension(name):
    return PurePosixPath(str(name)).suffix.lower().lstrip('.')

def media_kind(name):
    ext = extension(name)
    if ext in IMAGE_EXTENSIONS:
        return 'image' if ext not in ('heic', 'heif', 'tif', 'tiff') else 'file'
    if ext in VIDEO_EXTENSIONS: return 'video'
    if ext in AUDIO_EXTENSIONS: return 'audio'
    return 'file'

def validate_upload(upload):
    """Validate new uploads without re-reading historic or CSV-referenced files."""
    ext = extension(upload.name)
    if ext not in EXTENSIONS:
        raise ValidationError(_('Неподдерживаемый формат медиафайла.'))
    if upload.size > getattr(settings, 'MAX_MEDIA_UPLOAD_BYTES', 30 * 1024 ** 3):
        raise ValidationError(_('Размер медиафайла не должен превышать 30 ГБ.'))
    position = upload.tell()
    try:
        upload.seek(0)
        head = upload.read(256)
        if ext in IMAGE_EXTENSIONS and ext not in ('heic', 'heif'):
            from PIL import Image, UnidentifiedImageError
            try:
                upload.seek(0)
                with Image.open(upload) as image:
                    image.verify()
            except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
                raise ValidationError(_('Файл не является корректным изображением.')) from exc
            return upload
        checks = {
            'mp4': lambda h: h[4:8] == b'ftyp', 'm4v': lambda h: h[4:8] == b'ftyp',
            'm4a': lambda h: h[4:8] == b'ftyp', '3gp': lambda h: h[4:8] == b'ftyp',
            'heic': lambda h: h[4:8] == b'ftyp', 'heif': lambda h: h[4:8] == b'ftyp',
            'mov': lambda h: h[4:8] in (b'ftyp', b'moov', b'mdat', b'wide'),
            'webm': lambda h: h.startswith(b'\x1aE\xdf\xa3'), 'mkv': lambda h: h.startswith(b'\x1aE\xdf\xa3'),
            'weba': lambda h: h.startswith(b'\x1aE\xdf\xa3'),
            'avi': lambda h: h.startswith(b'RIFF') and h[8:12] == b'AVI ',
            'wav': lambda h: h.startswith(b'RIFF') and h[8:12] == b'WAVE',
            'flac': lambda h: h.startswith(b'fLaC'),
            'wma': lambda h: h.startswith(b'\x30\x26\xb2\x75\x8e\x66\xcf\x11'),
            'mp3': lambda h: h.startswith(b'ID3') or len(h)>1 and h[0]==255 and h[1]&224==224,
            'aac': lambda h: len(h)>1 and h[0]==255 and h[1]&246==240,
        }
        if ext in ('ogg','oga','ogv','opus'): valid = head.startswith(b'OggS')
        elif ext in ('aif','aiff'): valid = head.startswith(b'FORM') and head[8:12] in (b'AIFF',b'AIFC')
        elif ext in ('mpeg','mpg'): valid = head.startswith(b'\x00\x00\x01')
        else: valid = checks.get(ext, lambda h: False)(head)
        if not valid:
            raise ValidationError(_('Содержимое файла не соответствует выбранному формату.'))
        return upload
    finally:
        upload.seek(position)
