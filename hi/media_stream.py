"""Serve registered media with single HTTP byte ranges for movie seeking."""
import os
import re
from pathlib import Path
from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_http_methods
from .models import MediaContent


def stream_bytes(file, length):
    try:
        while length:
            data = file.read(min(length, 256 * 1024))
            if not data: break
            length -= len(data)
            yield data
    finally:
        file.close()


@require_http_methods(['GET', 'HEAD'])
def media_stream(request, pk):
    posts = MediaContent.objects.all()
    if not request.user.is_authenticated or not request.user.is_staff:
        posts = posts.filter(is_published=True)
    post = get_object_or_404(posts, pk=pk)
    file = None
    try:
        file = Path(post.local_path).open('rb') if post.local_path else post.image.open('rb')
        size = os.fstat(file.fileno()).st_size
    except (OSError, ValueError, NotImplementedError):
        if file: file.close()
        raise Http404
    start, end, partial = 0, size - 1, False
    header = request.headers.get('Range', '')
    # No validators are issued; an If-Range validator cannot match and requires full output.
    if header and not request.headers.get('If-Range'):
        match = re.fullmatch(r'bytes=(\d*)-(\d*)', header)
        try:
            if not match or not size: raise ValueError
            left, right = match.groups()
            if not left:
                count = int(right)
                if count <= 0: raise ValueError
                start = max(0, size - count)
            else:
                start = int(left); end = min(int(right), size-1) if right else size-1
            if start > end or start >= size: raise ValueError
            partial = True
        except ValueError:
            file.close()
            response = HttpResponse(status=416)
            response['Content-Range'] = f'bytes */{size}'
            response['Accept-Ranges'] = 'bytes'
            return response
    length = max(0, end - start + 1)
    content_type = post.media_mime or 'application/octet-stream'
    if request.method == 'HEAD':
        file.close(); response = HttpResponse(status=206 if partial else 200, content_type=content_type)
    elif partial:
        file.seek(start)
        response = StreamingHttpResponse(stream_bytes(file, length), status=206, content_type=content_type)
        response._resource_closers.append(file.close)
    else:
        response = FileResponse(file, content_type=content_type)
    response['Content-Length'] = str(length)
    response['Accept-Ranges'] = 'bytes'
    if partial: response['Content-Range'] = f'bytes {start}-{end}/{size}'
    response['Content-Disposition'] = content_disposition_header('download' in request.GET, post.media_name)
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, no-store'
    return response
