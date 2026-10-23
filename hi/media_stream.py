"""Permission-checked media delivery with bounded-memory HTTP byte ranges."""
import os
import re
from pathlib import Path
from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_http_methods
from .media_files import MIME_TYPES, extension
from .media_queries import visible_media, can_view_drafts
from .models import Developer, Profile, MediaContent


def stream_bytes(file, length):
    try:
        while length:
            data = file.read(min(length, 256 * 1024))
            if not data:
                break
            length -= len(data)
            yield data
    finally:
        file.close()


def bytes_response(request, file, content_type, name):
    size = os.fstat(file.fileno()).st_size
    start, end, partial = 0, size - 1, False
    header = request.headers.get('Range', '')
    if header and not request.headers.get('If-Range'):
        match = re.fullmatch(r'bytes=(\d*)-(\d*)', header)
        try:
            if not match or not size:
                raise ValueError
            left, right = match.groups()
            if not left:
                count = int(right)
                if count <= 0:
                    raise ValueError
                start = max(0, size - count)
            else:
                start = int(left)
                end = min(int(right), size - 1) if right else size - 1
            if start > end or start >= size:
                raise ValueError
            partial = True
        except ValueError:
            file.close()
            response = HttpResponse(status=416)
            response['Content-Range'] = f'bytes */{size}'
            response['Accept-Ranges'] = 'bytes'
            return response
    length = max(0, end - start + 1)
    if request.method == 'HEAD':
        file.close()
        response = HttpResponse(status=206 if partial else 200, content_type=content_type)
    elif partial:
        file.seek(start)
        response = StreamingHttpResponse(stream_bytes(file, length), status=206, content_type=content_type)
        response._resource_closers.append(file.close)
    else:
        response = FileResponse(file, content_type=content_type)
    response['Content-Length'] = str(length)
    response['Accept-Ranges'] = 'bytes'
    if partial:
        response['Content-Range'] = f'bytes {start}-{end}/{size}'
    response['Content-Disposition'] = content_disposition_header('download' in request.GET, name)
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, no-store'
    return response


@require_http_methods(['GET', 'HEAD'])
def media_stream(request, pk):
    post = MediaContent.objects.filter(pk=pk, is_published=True).first()
    if post is None:
        post = get_object_or_404(visible_media(request.user), pk=pk)
    try:
        file = Path(post.local_path).open('rb') if post.local_path else post.image.open('rb')
    except (OSError, ValueError, NotImplementedError):
        raise Http404
    return bytes_response(request, file, post.media_mime or 'application/octet-stream', post.media_name)


@require_http_methods(['GET', 'HEAD'])
def registered_media(request, path):
    """Keep legacy /media URLs while preventing direct access to draft assets."""
    from django.db.models import Q
    avatar = path.startswith('avatars/') and Profile.objects.filter(avatar=path).exists()
    portfolio = path.startswith('developer/') and Developer.objects.filter(photo=path).exists()
    if not (avatar or portfolio):
        references = MediaContent.objects.filter(Q(image=path) | Q(poster=path))
        if not references.filter(is_published=True).exists():
            if not can_view_drafts(request.user) or not references.exists():
                raise Http404
    try:
        full_path = (Path(settings.MEDIA_ROOT) / path).resolve()
        full_path.relative_to(Path(settings.MEDIA_ROOT).resolve())
        file = full_path.open('rb')
    except (OSError, ValueError):
        raise Http404
    response = bytes_response(request, file, MIME_TYPES.get(extension(path), 'application/octet-stream'), full_path.name)
    if avatar or portfolio:
        response['Cache-Control'] = 'private, max-age=3600'
    return response
