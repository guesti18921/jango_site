from rest_framework import serializers
from ..models import MediaContent


class MediaContentSerializer(serializers.ModelSerializer):
    average_rating = serializers.FloatField(read_only=True, allow_null=True)
    rating_count = serializers.IntegerField(read_only=True)
    comment_count = serializers.IntegerField(read_only=True)
    # Абсолютный URL картинки: http://127.0.0.1:8000/media/uploads/foo.jpg
    image = serializers.SerializerMethodField()
    poster = serializers.ImageField(use_url=True, read_only=True)

    # Имя автора строкой (а не id), удобно для мобильного приложения
    author = serializers.SerializerMethodField()

    class Meta:
        model = MediaContent
        fields = [
            'id', 'poster', 'media_kind', 'media_mime', 'media_name', 'average_rating', 'rating_count', 'comment_count',
            'title',
            'description',
            'image',
            'author',
            'is_published',
            'created_at',
            'updated_at',
        ]

    def get_image(self, obj):
        url = obj.media_url
        request = self.context.get('request')
        return request.build_absolute_uri(url) if request and url else url or None

    def get_author(self, obj):
        if obj.author:
            return {
                'id': obj.author.id,
                'username': obj.author.username,
            }
        return None