"""Console-only recovery for the local server. Codes never enter HTTP responses."""
import secrets
import uuid
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from .models import RecoveryState

SESSION_KEY = 'recovery_token'
CODE_LIFETIME = timedelta(minutes=10)
COOLDOWN = timedelta(seconds=60)
MAX_REQUESTS = 5
MAX_ATTEMPTS = 5


def password_fingerprint(user):
    return salted_hmac('hi.recovery.password', user.password).hexdigest()


def eligible_user(identifier):
    # Exact usernames take priority; an email must identify exactly one account.
    user = User.objects.filter(username=identifier).first()
    if user is None:
        matches = list(User.objects.filter(email__iexact=identifier)[:2])
        user = matches[0] if len(matches) == 1 else None
    if user and user.is_active and user.has_usable_password():
        return user
    return None


def issue_code(identifier):
    user = eligible_user(identifier)
    identity = f'user:{user.pk}' if user else f'unknown:{identifier.casefold()}'
    key = salted_hmac('hi.recovery.identity', identity, algorithm='sha256').hexdigest()
    now = timezone.now()
    state, _ = RecoveryState.objects.get_or_create(identity_key=key)
    if state.last_sent and now - state.last_sent < COOLDOWN:
        return None
    in_window = state.window_start and now - state.window_start < timedelta(hours=1)
    if in_window and state.request_count >= MAX_REQUESTS:
        return None
    code = f'{secrets.randbelow(1_000_000):06d}'
    token = uuid.uuid4()
    # Compare-and-swap prevents concurrent requests from bypassing throttling.
    changed = RecoveryState.objects.filter(
        pk=key, last_sent=state.last_sent, request_count=state.request_count,
    ).update(
        token=token, user=user, code_hash=make_password(code),
        password_fingerprint=password_fingerprint(user) if user else '',
        expires_at=now + CODE_LIFETIME, last_sent=now,
        window_start=state.window_start if in_window else now,
        request_count=state.request_count + 1 if in_window else 1,
        attempts=0, consumed=False,
    )
    if not changed:
        return None
    if user:
        print(
            '\n[ACCOUNT RECOVERY]\n'
            f'User: {user.username!r}\nCode: {code}\n'
            f'Request: {str(token)[:8]}\n'
            'Valid for 10 minutes. Enter only on the local recovery page.\n',
            flush=True,
        )
    return token


def get_state(token):
    try:
        return RecoveryState.objects.filter(token=uuid.UUID(str(token))).first()
    except (ValueError, TypeError, AttributeError):
        return None


def usable(state):
    return bool(state and not state.consumed and state.expires_at
                and state.expires_at > timezone.now() and state.attempts < MAX_ATTEMPTS)


@transaction.atomic
def confirm_code(token, data, form_class):
    try:
        token = uuid.UUID(str(token))
    except (ValueError, TypeError, AttributeError):
        return None, False, True
    # Write before reading so SQLite can serialize concurrent confirmations.
    reserved = RecoveryState.objects.filter(
        token=token, consumed=False,
        attempts__lt=MAX_ATTEMPTS, expires_at__gt=timezone.now(),
    ).update(attempts=F('attempts') + 1)
    if not reserved:
        return None, False, True
    state = get_state(token)
    user = User.objects.filter(pk=state.user_id).first()
    valid_user = bool(user and user.is_active and user.has_usable_password()
                      and constant_time_compare(state.password_fingerprint, password_fingerprint(user)))
    form = form_class(user or User(), data)
    valid_form = form.is_valid()
    valid_code = check_password(str(data.get('code', '')).strip(), state.code_hash)
    if not valid_code or not valid_user:
        form.add_error('code', 'Код неверен или больше не действует.')
    if valid_form and valid_code and valid_user:
        form.save()
        RecoveryState.objects.filter(pk=state.pk, token=state.token).update(consumed=True)
        return form, True, False
    return form, False, state.attempts >= MAX_ATTEMPTS
