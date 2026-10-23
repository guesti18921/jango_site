from django.urls import reverse


def layout(request):
    match = request.resolver_match
    next_url = request.get_full_path()
    # Validation pages may have a POST-only URL; language switching must return to a GET page.
    if match and match.url_name in ('add_comment', 'rate_post'):
        next_url = reverse('post_detail', args=[match.kwargs['pk']])
    return {'language_next': next_url}
