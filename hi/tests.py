import io
import re
from contextlib import redirect_stdout
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.hashers import check_password
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import RecoveryState
from .recovery import SESSION_KEY


class ConsoleRecoveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('artem', 'artem@example.com', 'Old!Password749')

    def request_code(self, identifier='artem', client=None):
        output = io.StringIO()
        with redirect_stdout(output):
            response = (client or self.client).post(reverse('recovery_request'), {'identifier': identifier})
        match = re.search(r'Code: ([0-9]{6})', output.getvalue())
        return response, match.group(1) if match else None, output.getvalue()

    def confirm(self, code, password='New!Secret5829', client=None):
        return (client or self.client).post(reverse('recovery_confirm'), {
            'code': code, 'new_password1': password, 'new_password2': password,
        })

    def test_complete_flow_console_only_and_old_password_rejected(self):
        with patch('django.core.mail.send_mail') as mail:
            response, code, output = self.request_code()
            self.assertRedirects(response, reverse('recovery_confirm'))
            self.assertRegex(code, r'^[0-9]{6}$')
            self.assertIn("User: 'artem'", output)
            state = RecoveryState.objects.get()
            self.assertNotEqual(state.code_hash, code)
            self.assertTrue(check_password(code, state.code_hash))
            self.assertEqual(self.client.session[SESSION_KEY], str(state.token))
            self.assertNotIn(code, self.client.get(reverse('recovery_confirm')).content.decode())
            self.assertRedirects(self.confirm(code), reverse('login'))
            self.assertTrue(RecoveryState.objects.get().consumed)
            self.assertNotIn(SESSION_KEY, self.client.session)
            self.assertFalse(self.client.login(username='artem', password='Old!Password749'))
            self.assertTrue(self.client.login(username='artem', password='New!Secret5829'))
            mail.assert_not_called()

    def test_email_lookup_is_case_insensitive(self):
        response, code, _ = self.request_code('ARTEM@example.com')
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(code)

    def test_unknown_identity_uses_same_page_without_console_code(self):
        response, code, output = self.request_code('unknown@example.com')
        self.assertRedirects(response, reverse('recovery_confirm'))
        self.assertIsNone(code)
        self.assertEqual(output, '')
        self.assertContains(self.confirm('123456'), 'Код неверен')

    def test_inactive_and_unusable_accounts_do_not_receive_codes(self):
        for username, active, password in [('inactive', False, 'Some!Password879'), ('nopass', True, None)]:
            User.objects.create_user(username, is_active=active, password=password)
            _, code, output = self.request_code(username)
            self.assertIsNone(code)
            self.assertEqual(output, '')

    def test_duplicate_email_requires_username(self):
        User.objects.create_user('other', 'artem@example.com', 'Another!Password749')
        _, code, _ = self.request_code('artem@example.com')
        self.assertIsNone(code)
        _, code, _ = self.request_code('artem')
        self.assertIsNotNone(code)

    def test_expired_code_cannot_change_password(self):
        _, code, _ = self.request_code()
        RecoveryState.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertRedirects(self.confirm(code), reverse('recovery_request'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Old!Password749'))

    def test_five_failed_attempts_invalidate_code(self):
        _, code, _ = self.request_code()
        wrong = '000001' if code != '000001' else '000002'
        for _ in range(4):
            self.assertContains(self.confirm(wrong), 'Код неверен')
        self.assertRedirects(self.confirm(wrong), reverse('recovery_request'))
        self.assertEqual(RecoveryState.objects.get().attempts, 5)
        self.assertRedirects(self.confirm(code), reverse('recovery_request'))

    def test_submitted_code_is_not_echoed_in_error_html(self):
        _, code, _ = self.request_code()
        response = self.confirm(code, '123')
        self.assertNotContains(response, f'value="{code}"')

    def test_malformed_code_counts_as_attempt(self):
        self.request_code()
        self.confirm('hello')
        self.assertEqual(RecoveryState.objects.get().attempts, 1)

    def test_weak_and_mismatched_passwords_are_rejected(self):
        _, code, _ = self.request_code()
        self.assertEqual(self.confirm(code, '123').status_code, 200)
        response = self.client.post(reverse('recovery_confirm'), {
            'code': code, 'new_password1': 'Good!Password927', 'new_password2': 'Different!927',
        })
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Old!Password749'))
        self.assertRedirects(self.confirm(code), reverse('login'))

    def test_resend_cooldown_applies_across_sessions_and_aliases(self):
        self.request_code()
        response, code, output = self.request_code('artem@example.com', Client())
        self.assertContains(response, 'Повторный запрос')
        self.assertIsNone(code)
        self.assertEqual(output, '')
        self.assertEqual(RecoveryState.objects.get().request_count, 1)

    def test_hourly_limit_and_reset(self):
        self.request_code()
        for _ in range(4):
            RecoveryState.objects.update(last_sent=timezone.now() - timedelta(seconds=61))
            _, code, _ = self.request_code()
            self.assertIsNotNone(code)
        RecoveryState.objects.update(last_sent=timezone.now() - timedelta(seconds=61))
        response, code, _ = self.request_code()
        self.assertContains(response, 'Не более 5 запросов')
        self.assertIsNone(code)
        RecoveryState.objects.update(window_start=timezone.now() - timedelta(hours=1, seconds=1))
        _, code, _ = self.request_code()
        self.assertIsNotNone(code)
        self.assertEqual(RecoveryState.objects.get().request_count, 1)

    def test_resend_invalidates_old_code_and_session(self):
        first_client = self.client
        with patch('hi.recovery.secrets.randbelow', return_value=111111):
            _, first_code, _ = self.request_code()
        RecoveryState.objects.update(last_sent=timezone.now() - timedelta(seconds=61))
        second_client = Client()
        with patch('hi.recovery.secrets.randbelow', return_value=222222):
            _, new_code, _ = self.request_code(client=second_client)
        self.assertRedirects(self.confirm(first_code, client=first_client), reverse('recovery_request'))
        self.assertContains(self.confirm(first_code, client=second_client), 'Код неверен')
        self.assertRedirects(self.confirm(new_code, client=second_client), reverse('login'))

    def test_code_cannot_be_replayed_even_if_session_is_restored(self):
        _, code, _ = self.request_code()
        token = self.client.session[SESSION_KEY]
        self.confirm(code)
        session = self.client.session
        session[SESSION_KEY] = token
        session.save()
        self.assertRedirects(self.confirm(code), reverse('recovery_request'))

    def test_confirm_requires_original_browser_session(self):
        _, code, _ = self.request_code()
        self.assertRedirects(self.confirm(code, client=Client()), reverse('recovery_request'))

    def test_admin_password_change_invalidates_outstanding_code(self):
        _, code, _ = self.request_code()
        self.user.set_password('Changed!Elsewhere294')
        self.user.save()
        self.assertContains(self.confirm(code), 'Код неверен')
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Changed!Elsewhere294'))

    def test_deactivated_user_cannot_recover_with_existing_code(self):
        _, code, _ = self.request_code()
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertContains(self.confirm(code), 'Код неверен')

    def test_recovery_pages_are_not_cached(self):
        for url in ['recovery_request', 'recovery_confirm']:
            response = self.client.get(reverse(url))
            self.assertIn('no-store', response['Cache-Control'])

    def test_csrf_is_required(self):
        strict = Client(enforce_csrf_checks=True)
        self.assertEqual(strict.post(reverse('recovery_request'), {'identifier': 'artem'}).status_code, 403)
        self.request_code(client=strict)  # still forbidden; no state is created
        self.assertEqual(strict.post(reverse('recovery_confirm'), {'code': '123456'}).status_code, 403)

    def test_old_email_reset_routes_are_removed(self):
        for path in ['/password-reset/', '/password-reset/done/', '/password-reset/abc/token/']:
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_new_design_pages_and_existing_profile_and_dashboard(self):
        for name in ['login', 'register', 'staff-login', 'recovery_request']:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertNotContains(self.client.get(reverse('login')), 'Забыли пароль?')
        self.client.force_login(self.user)
        for name in ['home', 'profile', 'profile_edit', 'app']:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertRedirects(self.client.get(reverse('recovery_request')), reverse('profile'))
        User.objects.filter(pk=self.user.pk).update(is_staff=True)
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)

    def test_success_invalidates_existing_login_sessions(self):
        other = Client()
        other.force_login(self.user)
        _, code, _ = self.request_code()
        self.confirm(code)
        self.assertRedirects(other.get(reverse('profile')), '/login/?next=/profile/')
