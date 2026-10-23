from django.utils.translation import gettext_lazy
from django.contrib import messages
from django.contrib.auth.models import User
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from .forms import RecoveryConfirmForm, RecoveryRequestForm
from .recovery import SESSION_KEY, confirm_code, get_state, issue_code, usable


@never_cache
@require_http_methods(['GET', 'POST'])
def recovery_request(request):
    if request.user.is_authenticated:
        return redirect('profile')
    form = RecoveryRequestForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        token = issue_code(form.cleaned_data['identifier'])
        if token is None:
            form.add_error(None, gettext_lazy('Повторный запрос доступен через минуту. Не более 5 запросов в час.'))
        else:
            request.session.cycle_key()
            request.session[SESSION_KEY] = str(token)
            return redirect('recovery_confirm')
    return render(request, 'hi/recovery_request.html', {'form': form})


@never_cache
@sensitive_post_parameters('code', 'new_password1', 'new_password2')
@require_http_methods(['GET', 'POST'])
def recovery_confirm(request):
    if request.user.is_authenticated:
        return redirect('profile')
    token = request.session.get(SESSION_KEY)
    state = get_state(token)
    if not usable(state):
        request.session.pop(SESSION_KEY, None)
        messages.error(request, gettext_lazy('Код истёк или попытки закончились. Запросите новый код.'))
        return redirect('recovery_request')
    if request.method == 'POST':
        form, success, blocked = confirm_code(token, request.POST, RecoveryConfirmForm)
        if success:
            request.session.pop(SESSION_KEY, None)
            request.session.cycle_key()
            messages.success(request, gettext_lazy('Пароль изменён. Войдите с новым паролем.'))
            return redirect('login')
        if blocked:
            request.session.pop(SESSION_KEY, None)
            messages.error(request, gettext_lazy('Код истёк или попытки закончились. Запросите новый код.'))
            return redirect('recovery_request')
    else:
        form = RecoveryConfirmForm(User())
    state.refresh_from_db()
    return render(request, 'hi/recovery_confirm.html', {
        'form': form, 'attempts_left': 5 - state.attempts,
        'request_id': str(state.token)[:8],
    })
