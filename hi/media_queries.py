"""Shared visibility policy and bounded-cost engagement summaries."""
from django.db.models import Avg, Count, IntegerField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce


def can_view_drafts(user):
    return bool(user.is_authenticated and user.is_active and user.is_staff and (
        user.has_perm('hi.view_mediacontent') or user.has_perm('hi.change_mediacontent')
    ))


def visible_media(user):
    from .models import MediaContent
    query = MediaContent.objects.all()
    return query if can_view_drafts(user) else query.filter(is_published=True)


def with_engagement(query):
    from .models import Comment, Rating
    ratings = Rating.objects.filter(post_id=OuterRef('pk')).order_by().values('post_id')
    comments = Comment.objects.filter(post_id=OuterRef('pk')).order_by().values('post_id')
    # Independent indexed subqueries avoid a ratings × comments join explosion.
    return query.annotate(
        average_rating=Subquery(ratings.annotate(value=Avg('value')).values('value')[:1]),
        rating_count=Coalesce(Subquery(ratings.annotate(total=Count('pk')).values('total')[:1]), Value(0), output_field=IntegerField()),
        comment_count=Coalesce(Subquery(comments.annotate(total=Count('pk')).values('total')[:1]), Value(0), output_field=IntegerField()),
    )
