from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import MediaContentViewSet


router = DefaultRouter()
router.register(r'media', MediaContentViewSet, basename='media')

urlpatterns = [
    path('', include(router.urls)),
]