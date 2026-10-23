from django.contrib.auth import views as auth_views
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from hi import views

urlpatterns = [
    # Django-админка (можно оставить на отдельный URL, например /django-admin/)
    path('django-admin/', admin.site.urls),

    # Основные страницы
    path('', views.index, name='home'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
        # Восстановление пароля
    path('password-reset/', auth_views.PasswordResetView.as_view(
        template_name='registration/password_reset_form.html',
        email_template_name='registration/password_reset_email.html',
        success_url='/password-reset/done/',
    ), name='password_reset'),

    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='registration/password_reset_done.html',
    ), name='password_reset_done'),

    path('password-reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='registration/password_reset_confirm.html',
        success_url='/password-reset/complete/',
    ), name='password_reset_confirm'),

    path('password-reset/complete/', auth_views.PasswordResetCompleteView.as_view(
        template_name='registration/password_reset_complete.html',
    ), name='password_reset_complete'),
    path('logout/', views.logout_view, name='logout'),

    # Профиль
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),

    # Админ-панель
    path('staff-login/', views.staff_login_view, name='staff-login'),
    path('dashboard/', views.dashboard, name='dashboard'),

    # API для мобильного приложения
    path('api/', include('hi.api.urls')),

    # Страница-тест API (для демонстрации мобильному клиенту)
    path('api-test/', views.api_test_view, name='api_test'),

        # Мобильное приложение (PWA)
    path('app/', views.app_view, name='app'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)