from rest_framework import serializers
from ..models import MediaContent


class MediaContentSerializer(serializers.ModelSerializer):
    # Абсолютный URL картинки: http://127.0.0.1:8000/media/uploads/foo.jpg
    image = serializers.ImageField(use_url=True)

    # Имя автора строкой (а не id), удобно для мобильного приложения
    author = serializers.SerializerMethodField()

    class Meta:
        model = MediaContent
        fields = [
            'id',
            'title',
            'description',
            'image',
            'author',
            'is_published',
            'created_at',
            'updated_at',
        ]

    def get_author(self, obj):
        if obj.author:
            return {
                'id': obj.author.id,
                'username': obj.author.username,
            }
        return None