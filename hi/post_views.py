from django.utils.translation import gettext_lazy
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Avg, Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from .forms import CommentForm, RatingForm
from .models import Comment, MediaContent, Rating
from .media_queries import visible_media


def visible_posts(user):
    return visible_media(user).select_related('author__profile')


def render_post(request, post, comment_form=None, rating_form=None, status=200):
    summary = post.ratings.aggregate(average=Avg('value'), total=Count('pk'))
    own_rating = post.ratings.filter(user=request.user).first()
    comments = Paginator(post.comments.select_related('user__profile'), 20).get_page(request.GET.get('page'))
    return render(request, 'hi/post_detail.html', {
        'post': post, 'summary': summary, 'own_rating': own_rating, 'comments': comments,
        'comment_form': comment_form if comment_form is not None else CommentForm(),
        'rating_form': rating_form if rating_form is not None else RatingForm(initial={'value': own_rating.value if own_rating else None}),
        'can_moderate': request.user.is_staff and request.user.has_perm('hi.delete_comment'),
    }, status=status)


@login_required
@require_GET
def post_detail(request, pk):
    return render_post(request, get_object_or_404(visible_posts(request.user), pk=pk))


@login_required
@require_POST
def add_comment(request, pk):
    post = get_object_or_404(visible_posts(request.user), pk=pk)
    form = CommentForm(request.POST)
    if not form.is_valid():
        return render_post(request, post, comment_form=form, status=400)
    Comment.objects.create(post=post, user=request.user, text=form.cleaned_data['text'])
    messages.success(request, gettext_lazy('Комментарий добавлен.'))
    return redirect(reverse('post_detail', args=[post.pk]) + '#comments')


@login_required
@require_POST
def rate_post(request, pk):
    post = get_object_or_404(visible_posts(request.user), pk=pk)
    form = RatingForm(request.POST)
    if not form.is_valid():
        return render_post(request, post, rating_form=form, status=400)
    Rating.objects.update_or_create(post=post, user=request.user, defaults={'value': form.cleaned_data['value']})
    messages.success(request, gettext_lazy('Ваша оценка сохранена.'))
    return redirect(reverse('post_detail', args=[post.pk]) + '#rating')


@login_required
@require_POST
def delete_comment(request, pk):
    comment = get_object_or_404(Comment.objects.select_related('post'), pk=pk, post__in=visible_posts(request.user))
    if comment.user_id != request.user.pk and not (request.user.is_staff and request.user.has_perm('hi.delete_comment')):
        raise PermissionDenied
    post_id = comment.post_id
    comment.delete()
    messages.success(request, gettext_lazy('Комментарий удалён.'))
    return redirect(reverse('post_detail', args=[post_id]) + '#comments')
