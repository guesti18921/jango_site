from django.utils.translation import gettext_lazy
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.contrib import messages
from .models import MediaContent, Profile
from django.db.models import Avg, Count
from .forms import (
    UserRegisterForm, UserLoginForm, StaffLoginForm,
    ProfileForm, UserForm,
)


def _is_staff(user):
    return user.is_authenticated and user.is_staff


# ============ ОБЫЧНЫЕ ПОЛЬЗОВАТЕЛИ ============

@login_required(login_url='login')
def index(request):
    all_media = MediaContent.objects.all()
    if not request.user.is_staff:
        all_media = all_media.filter(is_published=True)
    all_media = all_media.select_related('author__profile').annotate(
        average_rating=Avg('ratings__value'), rating_count=Count('ratings', distinct=True),
        comment_count=Count('comments', distinct=True),
    ).order_by('-created_at', '-pk')
    return render(request, 'hi/index.html', {'all_media': all_media})


def register_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, (gettext_lazy('Добро пожаловать, %(value0)s!') % {'value0': user.username}))
            return redirect('home')
    else:
        form = UserRegisterForm()

    return render(request, 'hi/register.html', {'form': form})


def login_view(request):
    """Обычный вход — для всех пользователей"""
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = UserLoginForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('home')
    else:
        form = UserLoginForm()

    return render(request, 'hi/login.html', {'form': form})


def staff_login_view(request):
    """Отдельный вход ТОЛЬКО для админов"""
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect('dashboard')
        return redirect('home')

    if request.method == 'POST':
        form = StaffLoginForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, gettext_lazy("Доступ запрещён. Это вход только для администраторов."))
    else:
        form = StaffLoginForm()

    return render(request, 'hi/staff_login.html', {'form': form})


@login_required(login_url='login')
def profile_view(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    user_media_count = MediaContent.objects.filter(author=request.user).count()
    return render(request, 'hi/profile.html', {
        'profile': profile,
        'user_media_count': user_media_count,
    })


@login_required(login_url='login')
def profile_edit(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        u_form = UserForm(request.POST, instance=request.user)
        p_form = ProfileForm(request.POST, request.FILES, instance=profile)
        if u_form.is_valid() and p_form.is_valid():
            u_form.save()
            p_form.save()
            messages.success(request, gettext_lazy("Профиль обновлён!"))
            return redirect('profile')
    else:
        u_form = UserForm(instance=request.user)
        p_form = ProfileForm(instance=profile)

    return render(request, 'hi/profile_edit.html', {
        'u_form': u_form,
        'p_form': p_form,
    })


def logout_view(request):
    logout(request)
    return redirect('login')


# ============ АДМИН-ПАНЕЛЬ ============

from .dashboard_views import dashboard


# ============ СТРАНИЦА-ТЕСТ API ============

@login_required(login_url='login')
def api_test_view(request):
    """
    Страница /api-test/ — демонстрация того, как мобильное приложение
    получит данные через API.
    """
    return render(request, 'hi/api-test.html')

@login_required(login_url='login')
def app_view(request):
    """Страница приложения /app/ — PWA-версия для телефона."""
    return render(request, 'hi/app.html')