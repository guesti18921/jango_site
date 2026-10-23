"""Permission-aware editorial management workspace."""
from django.contrib import messages
from django.contrib.admin.models import CHANGE, DELETION, LogEntry
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import HttpResponseBadRequest
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods
from .models import Comment, MediaContent, Rating


def can_view(user, model):
    return user.has_perm(f'{model._meta.app_label}.view_{model._meta.model_name}') or user.has_perm(f'{model._meta.app_label}.change_{model._meta.model_name}')


def log_action(user, obj, action, message):
    LogEntry.objects.create(user=user, content_type=ContentType.objects.get_for_model(obj), object_id=str(obj.pk), object_repr=str(obj)[:200], action_flag=action, change_message=message)


@user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url='staff-login')
@require_http_methods(['GET', 'POST'])
def dashboard(request):
    user = request.user
    if request.method == 'POST':
        action = request.POST.get('action')
        if action in ('publish', 'draft'):
            if not user.has_perm('hi.change_mediacontent'):
                raise PermissionDenied
            ids = request.POST.getlist('selected')
            if not ids or len(ids) > 100 or any(not i.isascii() or not i.isdecimal() or len(i) > 18 for i in ids):
                messages.error(request, _('Выберите от 1 до 100 публикаций.'))
            else:
                with transaction.atomic():
                    posts = list(MediaContent.objects.filter(pk__in=ids))
                    for post in posts:
                        post.is_published = action == 'publish'
                        post.updated_at = timezone.now()
                        post.save(update_fields=['is_published', 'updated_at'])
                        log_action(user, post, CHANGE, 'Published from dashboard' if post.is_published else 'Moved to drafts from dashboard')
                messages.success(request, _('Обновлено публикаций: %(count)s.') % {'count': len(posts)})
        elif action == 'delete_comment':
            if not user.has_perm('hi.delete_comment'):
                raise PermissionDenied
            comment_id = request.POST.get('comment_id', '')
            if not comment_id.isascii() or not comment_id.isdecimal() or len(comment_id) > 18:
                return HttpResponseBadRequest()
            with transaction.atomic():
                comment = get_object_or_404(Comment, pk=comment_id)
                log_action(user, comment, DELETION, 'Comment deleted from dashboard')
                comment.delete()
            messages.success(request, _('Комментарий удалён.'))
        else:
            messages.error(request, _('Неизвестное действие.'))
        # The query belongs to this URL, so returning to it cannot redirect off-site.
        return redirect(request.get_full_path())

    section = request.GET.get('section', 'overview')
    if section not in ('overview', 'posts', 'comments', 'users'):
        section = 'overview'
    view_posts, view_comments, view_users = (can_view(user, m) for m in (MediaContent, Comment, User))
    if section != 'overview' and not {'posts': view_posts, 'comments': view_comments, 'users': view_users}[section]:
        raise PermissionDenied
    q = request.GET.get('q', '').strip()[:200]
    status = request.GET.get('status', '')
    layout = 'grid' if request.GET.get('layout') == 'grid' else 'list'
    posts = MediaContent.objects.select_related('author__profile').annotate(
        average_rating=Avg('ratings__value'), comment_count=Count('comments', distinct=True),
    ).order_by('-created_at', '-pk')
    if q:
        posts = posts.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(author__username__icontains=q))
    counts = MediaContent.objects.aggregate(total=Count('pk'), published=Count('pk', filter=Q(is_published=True)), drafts=Count('pk', filter=Q(is_published=False))) if view_posts else {}
    if status in ('published', 'draft'):
        posts = posts.filter(is_published=status == 'published')
    comments = Comment.objects.select_related('user__profile', 'post').order_by('-created_at', '-pk')
    users = User.objects.select_related('profile').order_by('-date_joined', '-pk')
    if q and section == 'comments':
        comments = comments.filter(Q(text__icontains=q) | Q(user__username__icontains=q) | Q(post__title__icontains=q))
    if q and section == 'users':
        users = users.filter(Q(username__icontains=q) | Q(first_name__icontains=q) | Q(email__icontains=q))
    source = comments if section == 'comments' else users if section == 'users' else posts if view_posts else MediaContent.objects.none()
    page = Paginator(source, 12).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)
    tab_params = params.copy()
    tab_params.pop('status', None)
    titles = {'overview': _('Обзор'), 'posts': _('Публикации'), 'comments': _('Комментарии'), 'users': _('Пользователи')}
    return render(request, 'hi/dashboard.html', {
        'total_media': counts.get('total', 0), 'published_media': counts.get('published', 0),
        'total_staff': User.objects.filter(is_staff=True).count() if view_users else None,
        'average_rating': Rating.objects.aggregate(value=Avg('value'))['value'] if view_posts else None,
        'media_page': page, 'query': q, 'recent_users': users[:4] if view_users else [],
        'management': True, 'section': section, 'section_title': titles[section],
        'view_posts': view_posts, 'view_comments': view_comments, 'view_users': view_users,
        'counts': counts, 'total_comments': Comment.objects.count() if view_comments else None,
        'total_users': User.objects.count() if view_users else None,
        'recent_comments': comments[:3] if view_comments else [], 'page': page,
        'q': q, 'status': status, 'layout': layout, 'page_query': params.urlencode(),
        'tab_query': tab_params.urlencode(),
    })
