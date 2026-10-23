from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.i18n import JavaScriptCatalog
from django.views.decorators.cache import never_cache
from hi import views, recovery_views, csv_views, post_views, upload_views, media_stream

urlpatterns = [
    path('jsi18n/', never_cache(JavaScriptCatalog.as_view(packages=['hi'])), name='javascript-catalog'),
    path('i18n/', include('django.conf.urls.i18n')),
    # Django-админка (можно оставить на отдельный URL, например /django-admin/)
    path('django-admin/', admin.site.urls),

    # Основные страницы
    path('', views.index, name='home'),
    path('posts/<int:pk>/', post_views.post_detail, name='post_detail'),
    path('posts/<int:pk>/comment/', post_views.add_comment, name='add_comment'),
    path('posts/<int:pk>/rate/', post_views.rate_post, name='rate_post'),
    path('comments/<int:pk>/delete/', post_views.delete_comment, name='delete_comment'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    # Восстановление через одноразовый код в консоли сервера
    path('recover/', recovery_views.recovery_request, name='recovery_request'),
    path('recover/confirm/', recovery_views.recovery_confirm, name='recovery_confirm'),
    path('logout/', views.logout_view, name='logout'),

    # Профиль
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),

    # Админ-панель
    path('staff-login/', views.staff_login_view, name='staff-login'),
    path('files/<int:pk>/', media_stream.media_stream, name='media_stream'),
    path('dashboard/uploads/', upload_views.upload_page, name='upload_page'),
    path('dashboard/uploads/start/', upload_views.start_upload, name='upload_start'),
    path('dashboard/uploads/session/<uuid:pk>/', upload_views.upload_part, name='upload_part'),
    path('dashboard/uploads/session/<uuid:pk>/finish/', upload_views.finish_upload, name='upload_finish'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('dashboard/csv/export/', csv_views.export_media, name='csv_export'),
    path('dashboard/csv/import/', csv_views.import_media, name='csv_import'),

    # API для мобильного приложения
    path('api/', include('hi.api.urls')),

    # Страница-тест API (для демонстрации мобильному клиенту)
    path('api-test/', views.api_test_view, name='api_test'),

        # Мобильное приложение (PWA)
    path('app/', views.app_view, name='app'),
]

# Media must go through the same visibility policy as posts, including in DEBUG.
urlpatterns += [path('media/<path:path>', media_stream.registered_media, name='registered_media')]

handler400 = 'hi.error_views.bad_request'
handler403 = 'hi.error_views.permission_denied'
handler404 = 'hi.error_views.not_found'
handler500 = 'hi.error_views.server_error'
