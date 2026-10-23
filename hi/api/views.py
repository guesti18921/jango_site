from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from ..models import MediaContent
from ..media_queries import with_engagement
from .serializers import MediaContentSerializer


class MediaContentViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API для медиа-контента.

    GET /api/media/         — список (только is_published=True)
    GET /api/media/<id>/    — детали одного медиа
    """
    serializer_class = MediaContentSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        # Только опубликованное, свежие — первыми, автор подгружается сразу
        return with_engagement(MediaContent.objects.filter(is_published=True).select_related('author')).order_by('-created_at', '-pk')
