from django.apps import AppConfig


class HiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'hi'
    def ready(self):
        from . import media_lifecycle  # noqa: F401 — register file lifecycle hooks
