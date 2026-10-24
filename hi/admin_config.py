from django.contrib.admin.apps import AdminConfig


class VeyraAdminConfig(AdminConfig):
    default_site = 'hi.admin_site.VeyraAdminSite'
