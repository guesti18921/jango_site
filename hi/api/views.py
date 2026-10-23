from django.db.models import Avg, Count
from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from ..models import MediaContent
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
        return (
            MediaContent.objects
            .filter(is_published=True)
            .select_related('author')
            .annotate(average_rating=Avg('ratings__value'), rating_count=Count('ratings', distinct=True), comment_count=Count('comments', distinct=True))
            .order_by('-created_at', '-pk')
        )