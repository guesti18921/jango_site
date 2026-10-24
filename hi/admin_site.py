from django.contrib.admin import AdminSite
from django.utils.translation import gettext_lazy as _


class VeyraAdminSite(AdminSite):
    index_template = 'admin/veyra_index.html'
    app_index_template = 'admin/veyra_index.html'

    def gallery_context(self, request, app_label=None):
        # Reuse Django's model permissions and existing admin URLs. Never build
        # an unrestricted registry list for display to a limited staff account.
        apps = self.get_app_list(request, None if app_label == 'hi' else app_label)
        models = {}
        for app in apps:
            for model in app['models']:
                key = model['model']._meta.label_lower
                models[key] = {**model, 'key': key}
        primary = []
        for key, icon, description in (
            ('hi.mediacontent', 'i-feed', _('Фото, видео и аудио вашей коллекции.')),
            ('hi.comment', 'i-comment', _('Обсуждения под публикациями.')),
            ('auth.user', 'i-profile', _('Аккаунты и доступ к сайту.')),
        ):
            item = models.pop(key, None)
            if item:
                primary.append({**item, 'icon': icon, 'description': description})
        legacy_keys = {
            'hi.developer', 'hi.skill', 'hi.experience', 'hi.project',
            'hi.education', 'hi.company', 'hi.stat', 'hi.companyvalue',
            'hi.teammember', 'hi.historyitem',
        }
        additional, secondary = [], []
        for key, model in models.items():
            (additional if key in legacy_keys else secondary).append(model)
        return {
            'title': _('Управление галереей'),
            'gallery_primary': primary,
            'gallery_secondary': secondary,
            'gallery_additional': additional,
            'gallery_can_upload': request.user.has_perm('hi.add_mediacontent'),
        }

    def index(self, request, extra_context=None):
        context = {**self.gallery_context(request), **(extra_context or {})}
        return super().index(request, extra_context=context)

    def app_index(self, request, app_label, extra_context=None):
        context = {**self.gallery_context(request, app_label), **(extra_context or {})}
        return super().app_index(request, app_label, extra_context=context)
