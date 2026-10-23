"""Reject oversized form bodies before CSRF parsing can spool them to disk."""
from django.conf import settings
from django.http import JsonResponse
from django.utils.translation import gettext as _
from .error_views import error_page


class UploadBodyLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method not in ('POST', 'PUT', 'PATCH'):
            return self.get_response(request)
        path = request.path_info
        limit = 112 * 1024 ** 2  # Legacy media form: 100 MB file + 10 MB poster + metadata.
        if path.startswith('/dashboard/uploads/'):
            if path.endswith('/finish/'):
                limit = 11 * 1024 ** 2
            elif path.endswith('/start/'):
                limit = 8192
            elif request.method == 'PUT':
                limit = settings.MEDIA_CHUNK_BYTES
        elif path.startswith(('/profile/edit/', '/django-admin/hi/profile/')):
            limit = 12 * 1024 ** 2
        elif path.startswith('/dashboard/csv/import/'):
            limit = 2 * 1024 ** 2
        raw = request.META.get('CONTENT_LENGTH', '')
        invalid = bool(raw and (len(raw) > 12 or not raw.isascii() or not raw.isdecimal()))
        too_large = invalid or (raw and int(raw) > limit)
        if too_large:
            if path.startswith('/dashboard/uploads/'):
                return JsonResponse({'error': _('Запрос слишком большой. Для больших файлов используйте загрузку частями.')}, status=413)
            return error_page(request, 413)
        return self.get_response(request)
