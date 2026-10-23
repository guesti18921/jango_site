import json
import os
import re
from datetime import timedelta
from pathlib import Path
from django.conf import settings
from django.contrib.admin.models import ADDITION, LogEntry
from django.contrib.auth.decorators import user_passes_test
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.files import File
from django.db import DatabaseError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache
from .forms import UploadPublishForm
from .large_uploads import upload_lock, UploadBusy, partial_path, available_bytes, has_capacity, discard_expired, final_path
from .media_files import EXTENSIONS, extension, validate_upload
from .models import MediaContent, MediaUpload


def allowed(user):
    return user.is_authenticated and user.is_active and user.is_staff and user.has_perm('hi.add_mediacontent')


def error(message, status=400, **extra):
    return JsonResponse({'error': str(message), **extra}, status=status)


def manifest(upload):
    return {'id': str(upload.pk), 'offset': upload.offset, 'size': upload.size,
            'name': upload.name, 'state': upload.state, 'chunk_size': settings.MEDIA_CHUNK_BYTES,
            'post_url': reverse('post_detail', args=[upload.post_id]) if upload.post_id else None}



def owned(request, pk):
    return get_object_or_404(MediaUpload, pk=pk, user=request.user)


@user_passes_test(allowed, login_url='staff-login')
@never_cache
@require_http_methods(['GET'])
def upload_page(request):
    return render(request, 'hi/upload.html', {'section_title': _('Загрузка файлов'),
        'section': 'uploads', 'view_posts': True, 'form': UploadPublishForm(),
        'accept': ','.join('.' + ext for ext in EXTENSIONS), 'max_bytes': settings.MAX_MEDIA_UPLOAD_BYTES})


@never_cache
@require_http_methods(['POST'])
def start_upload(request):
    if not allowed(request.user): return error(_('Нет прав для загрузки.'), 403)
    raw_length = request.META.get('CONTENT_LENGTH', '')
    if raw_length and (len(raw_length) > 10 or not raw_length.isascii() or not raw_length.isdecimal() or int(raw_length) > 8192):
        return error(_('Некорректный запрос.'), 413)
    try:
        data = json.loads(request.read(8193))
        if not isinstance(data, dict): raise ValueError
        name, size, fingerprint = data.get('name'), data.get('size'), data.get('fingerprint')
        if not isinstance(name, str) or not name or len(name) > 200 or '/' in name or '\\' in name or any(ord(c)<32 for c in name): raise ValueError
        name.encode('utf-8')
        if type(size) is not int or not 0 < size <= settings.MAX_MEDIA_UPLOAD_BYTES: raise ValueError
        if not isinstance(fingerprint, str) or not re.fullmatch('[a-f0-9]{64}', fingerprint): raise ValueError
        if extension(name) not in EXTENSIONS: return error(_('Неподдерживаемый формат медиафайла.'))
    except (ValueError, TypeError, UnicodeError):
        return error(_('Проверьте имя и размер файла: максимум 30 ГБ.'))
    try:
        with upload_lock('capacity'):
            discard_expired()
            existing = MediaUpload.objects.filter(user=request.user, name=name, size=size,
                fingerprint=fingerprint, state='uploading', expires_at__gt=timezone.now()).first()
            if existing: return JsonResponse(manifest(existing))
            if not has_capacity(size): return error(_('На сервере недостаточно свободного места для этого файла.'), 507)
            if MediaUpload.objects.filter(user=request.user, state='uploading', expires_at__gt=timezone.now()).count() >= 5:
                return error(_('Сначала завершите или отмените предыдущие загрузки.'), 429)
            upload = MediaUpload.objects.create(user=request.user, name=name, size=size, fingerprint=fingerprint,
                expires_at=timezone.now() + timedelta(days=settings.MEDIA_UPLOAD_TTL_DAYS))
            try: partial_path(upload).touch(exist_ok=False)
            except OSError:
                upload.delete()
                raise
            return JsonResponse(manifest(upload), status=201)
    except UploadBusy: return error(_('Сервер занят, повторите запрос.'), 409)
    except DatabaseError: return error(_('База данных занята. Повторите запрос: сохранённые части не потеряны.'), 503)
    except OSError: return error(_('Не удалось подготовить файл. Проверьте место и доступ к папкам сервера.'), 507)


@never_cache
@require_http_methods(['GET', 'PUT', 'DELETE'])
def upload_part(request, pk):
    if not allowed(request.user): return error(_('Нет прав для загрузки.'), 403)
    upload = owned(request, pk)
    if request.method == 'GET': return JsonResponse(manifest(upload), status=410 if upload.expires_at <= timezone.now() and upload.state == 'uploading' else 200)
    try:
        with upload_lock(upload.pk):
            upload.refresh_from_db()
            if request.method == 'DELETE':
                if upload.state == 'completed': return error(_('Файл уже опубликован.'), 409)
                partial_path(upload).unlink(missing_ok=True)
                final_path(upload).unlink(missing_ok=True)
                upload.state = 'cancelled'; upload.save(update_fields=['state'])
                return JsonResponse(manifest(upload))
            if upload.expires_at <= timezone.now(): return error(_('Срок загрузки истёк. Выберите файл заново.'), 410)
            if upload.state != 'uploading': return error(_('Загрузка уже завершена или отменена.'), 409, **manifest(upload))
            try: offset = int(request.headers.get('X-Upload-Offset', '-1'))
            except ValueError: offset = -1
            if offset != upload.offset: return error(_('Продолжаем с сохранённой позиции.'), 409, **manifest(upload))
            length = min(settings.MEDIA_CHUNK_BYTES, upload.size - upload.offset)
            raw_length = request.META.get('CONTENT_LENGTH', '')
            if len(raw_length) > 10 or not raw_length.isascii() or not raw_length.isdecimal() or int(raw_length) != length or not length:
                return error(_('Некорректный размер части файла.'), 413)
            chunk = request.read(length + 1)
            if len(chunk) != length: return error(_('Часть файла получена не полностью.'))
            if available_bytes() < length + settings.MEDIA_UPLOAD_RESERVE_BYTES:
                return error(_('На сервере закончилось свободное место. Загрузка приостановлена.'), 507)
            if upload.offset == 0:
                partial_path(upload).touch(exist_ok=True)
            with transaction.atomic():
                with partial_path(upload).open('r+b') as file:
                    # DB offset is authoritative after a crash between disk write and DB commit.
                    if file.seek(0, os.SEEK_END) < upload.offset:
                        return error(_('Временный файл повреждён. Отмените загрузку и выберите файл заново.'), 409)
                    file.seek(upload.offset); file.truncate(); file.write(chunk); file.flush(); os.fsync(file.fileno())
                upload.offset += length
                upload.expires_at = timezone.now() + timedelta(days=settings.MEDIA_UPLOAD_TTL_DAYS)
                upload.save(update_fields=['offset', 'expires_at'])
            return JsonResponse(manifest(upload))
    except UploadBusy: return error(_('Другая часть ещё сохраняется. Повторите запрос.'), 409)
    except DatabaseError: return error(_('База данных занята. Повторите запрос: сохранённые части не потеряны.'), 503)
    except OSError: return error(_('Не удалось сохранить часть файла. Проверьте место на диске.'), 507)


@never_cache
@require_http_methods(['POST'])
def finish_upload(request, pk):
    if not allowed(request.user): return error(_('Нет прав для загрузки.'), 403)
    upload = owned(request, pk)
    # This request only contains metadata and a small optional poster.
    content_length = request.META.get('CONTENT_LENGTH') or '0'
    if len(content_length) > 10 or not content_length.isascii() or not content_length.isdecimal() or int(content_length) > 11 * 1024 ** 2:
        return error(_('Постер не должен превышать 10 МБ.'), 413)
    try:
        with upload_lock(upload.pk):
            upload.refresh_from_db()
            if upload.state == 'completed': return JsonResponse(manifest(upload))
            form = UploadPublishForm(request.POST, request.FILES)
            if not form.is_valid():
                return JsonResponse({'error': _('Проверьте поля публикации.'), 'fields': form.errors.get_json_data()}, status=400)
            if upload.state != 'uploading' or upload.expires_at <= timezone.now(): return error(_('Срок загрузки истёк. Выберите файл заново.'), 410)
            if upload.offset != upload.size: return error(_('Дождитесь завершения передачи файла.'), 409)
            source = partial_path(upload)
            # A process may die after rename but before its DB transaction commits.
            if not source.exists() and final_path(upload).is_file():
                os.replace(final_path(upload), source)
            if not source.exists() or source.stat().st_size < upload.size: return error(_('Временный файл повреждён.'), 409)
            with source.open('r+b') as handle:
                handle.truncate(upload.size)
                validate_upload(File(handle, name=upload.name))
            name = f'uploads/{upload.pk}.{extension(upload.name)}'
            destination = Path(settings.MEDIA_ROOT) / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Never copy a full movie; rename on the same disk. Recover the staged
            # file on a normal DB failure, and persist the final path for crash repair.
            os.replace(source, destination)
            post = None
            try:
                with transaction.atomic():
                    values = form.cleaned_data
                    post = MediaContent(title=values['title'], description=values['description'],
                        image=name, poster=values.get('poster') or '', author=request.user, is_published=values['is_published'])
                    post.save()
                    upload.state = 'completed'; upload.post = post
                    upload.save(update_fields=['state', 'post'])
                    LogEntry.objects.create(user=request.user, content_type=ContentType.objects.get_for_model(post),
                        object_id=str(post.pk), object_repr=post.title, action_flag=ADDITION, change_message='Resumable media upload')
            except Exception:
                os.replace(destination, source)
                if post and post.poster: post.poster.delete(save=False)
                raise
            return JsonResponse(manifest(upload), status=201)
    except ValidationError as exc: return error(' '.join(exc.messages))
    except UploadBusy: return error(_('Файл ещё сохраняется. Повторите запрос.'), 409)
    except DatabaseError: return error(_('База данных занята. Повторите запрос: сохранённые части не потеряны.'), 503)
    except OSError: return error(_('Не удалось завершить загрузку. Проверьте диск сервера.'), 507)
