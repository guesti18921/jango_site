from django.apps import AppConfig
from django.utils.translation import gettext_lazy


class HiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'hi'
    verbose_name = gettext_lazy('Медиаколлекция')
    def ready(self):
        from . import media_lifecycle  # noqa: F401 — register file lifecycle hooks
