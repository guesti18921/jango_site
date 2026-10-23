import io
from unittest.mock import patch

from django.contrib.auth.models import Permission, User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .management.commands.runlan import discover_addresses, private_ipv4
from .models import Comment, MediaContent, Rating


class PostInteractionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user('alice', password='Alice!Local829')
        cls.bob = User.objects.create_user('bob', password='Bob!Local829')
        cls.admin = User.objects.create_superuser('moderator', password='Admin!Local829')
        cls.staff = User.objects.create_user('staff_reader', is_staff=True)
        cls.post = MediaContent.objects.create(title='Пост для обсуждения', image='uploads/test.jpg', author=cls.admin)
        cls.draft = MediaContent.objects.create(title='Скрытый пост', image='uploads/test.jpg', is_published=False)

    def setUp(self):
        self.client.force_login(self.alice)

    def test_comment_persists_with_authenticated_author_and_escapes_html(self):
        response = self.client.post(reverse('add_comment', args=[self.post.pk]), {'text': '<script>alert(1)</script>\nХороший пост', 'user': self.bob.pk})
        self.assertEqual(response.status_code, 302)
        comment = Comment.objects.get()
        self.assertEqual(comment.user, self.alice)
        detail = self.client.get(reverse('post_detail', args=[self.post.pk]))
        self.assertContains(detail, '&lt;script&gt;')
        self.assertNotContains(detail, '<script>alert(1)</script>')
        self.assertContains(detail, 'Хороший пост')

    def test_empty_and_overlong_comments_rejected(self):
        for text in ['', '   \n ', 'x' * 2001]:
            self.assertEqual(self.client.post(reverse('add_comment', args=[self.post.pk]), {'text': text}).status_code, 400)
        self.assertFalse(Comment.objects.exists())

    def test_rating_changes_instead_of_creating_duplicate(self):
        for score in [2, 5]:
            response = self.client.post(reverse('rate_post', args=[self.post.pk]), {'value': score, 'user': self.bob.pk})
            self.assertEqual(response.status_code, 302)
        self.assertEqual(Rating.objects.count(), 1)
        rating = Rating.objects.get()
        self.assertEqual((rating.user_id, rating.value), (self.alice.pk, 5))
        self.assertContains(self.client.get(reverse('post_detail', args=[self.post.pk])), 'Изменить оценку')

    def test_out_of_range_ratings_rejected_by_form_and_database(self):
        for score in ['', '0', '6', '-1', '1.5', 'hello']:
            self.assertEqual(self.client.post(reverse('rate_post', args=[self.post.pk]), {'value': score}).status_code, 400)
        self.assertFalse(Rating.objects.exists())
        for score in [0, 6]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                Rating.objects.create(post=self.post, user=self.alice, value=score)

    def test_database_enforces_one_rating_per_person(self):
        Rating.objects.create(post=self.post, user=self.alice, value=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Rating.objects.create(post=self.post, user=self.alice, value=5)

    def test_average_and_counts_are_correct_with_multiple_comments(self):
        Rating.objects.create(post=self.post, user=self.alice, value=2)
        Rating.objects.create(post=self.post, user=self.bob, value=5)
        for n in range(3):
            Comment.objects.create(post=self.post, user=self.bob, text=str(n))
        card = self.client.get(reverse('home')).context['all_media'].get(pk=self.post.pk)
        self.assertEqual(card.average_rating, 3.5)
        self.assertEqual(card.rating_count, 2)
        self.assertEqual(card.comment_count, 3)
        self.assertEqual(self.client.get(reverse('post_detail', args=[self.post.pk])).context['summary'], {'average': 3.5, 'total': 2})

    def test_only_owner_or_authorized_moderator_can_delete(self):
        comment = Comment.objects.create(post=self.post, user=self.alice, text='Комментарий')
        endpoint = reverse('delete_comment', args=[comment.pk])
        self.client.force_login(self.bob)
        self.assertEqual(self.client.post(endpoint).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(endpoint).status_code, 403)
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(endpoint).status_code, 405)
        self.assertEqual(self.client.post(endpoint).status_code, 302)
        self.assertFalse(Comment.objects.exists())
        comment = Comment.objects.create(post=self.post, user=self.alice, text='Модерация')
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse('delete_comment', args=[comment.pk])).status_code, 302)
        self.assertFalse(Comment.objects.exists())

    def test_staff_with_moderation_permission_can_delete(self):
        self.staff.user_permissions.add(Permission.objects.get(codename='delete_comment'))
        comment = Comment.objects.create(post=self.post, user=self.alice, text='Модерация')
        self.client.force_login(self.staff)
        self.assertEqual(self.client.post(reverse('delete_comment', args=[comment.pk])).status_code, 302)

    def test_guests_cannot_read_or_write_interactions(self):
        guest = Client()
        self.assertEqual(guest.get(reverse('post_detail', args=[self.post.pk])).status_code, 302)
        for name, data in [('add_comment', {'text': 'test'}), ('rate_post', {'value': 5})]:
            self.assertEqual(guest.post(reverse(name, args=[self.post.pk]), data).status_code, 302)
        self.assertFalse(Comment.objects.exists())
        self.assertFalse(Rating.objects.exists())

    def test_hidden_posts_and_interactions_unavailable_to_regular_users(self):
        comment = Comment.objects.create(post=self.draft, user=self.alice, text='Раньше был виден')
        self.assertNotContains(self.client.get(reverse('home')), 'Скрытый пост')
        self.assertEqual(self.client.get(reverse('post_detail', args=[self.draft.pk])).status_code, 404)
        for name, data in [('add_comment', {'text': 'test'}), ('rate_post', {'value': 5})]:
            self.assertEqual(self.client.post(reverse(name, args=[self.draft.pk]), data).status_code, 404)
        self.assertEqual(self.client.post(reverse('delete_comment', args=[comment.pk])).status_code, 404)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('post_detail', args=[self.draft.pk])).status_code, 200)

    def test_writes_require_post_and_csrf(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.alice)
        for name in ['add_comment', 'rate_post']:
            endpoint = reverse(name, args=[self.post.pk])
            self.assertEqual(self.client.get(endpoint).status_code, 405)
            self.assertEqual(strict.post(endpoint, {'text': 'test', 'value': 5}).status_code, 403)
        comment = Comment.objects.create(post=self.post, user=self.alice, text='test')
        self.assertEqual(strict.post(reverse('delete_comment', args=[comment.pk])).status_code, 403)

    def test_comments_paginated_and_admin_moderation_lists_work(self):
        Comment.objects.bulk_create([Comment(post=self.post, user=self.bob, text=f'Комментарий {n}') for n in range(21)])
        first = self.client.get(reverse('post_detail', args=[self.post.pk]))
        self.assertEqual(len(first.context['comments']), 20)
        second = self.client.get(reverse('post_detail', args=[self.post.pk]) + '?page=2')
        self.assertEqual(len(second.context['comments']), 1)
        self.assertEqual(self.client.get(reverse('post_detail', args=[self.post.pk]) + '?page=bad').status_code, 200)
        self.client.force_login(self.admin)
        for url in ['/django-admin/hi/comment/', '/django-admin/hi/rating/']:
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_deleting_post_cascades_comments_and_ratings(self):
        Comment.objects.create(post=self.post, user=self.alice, text='test')
        Rating.objects.create(post=self.post, user=self.alice, value=4)
        self.post.delete()
        self.assertFalse(Comment.objects.exists())
        self.assertFalse(Rating.objects.exists())


class LANCommandTests(TestCase):
    def test_only_private_ipv4_addresses_are_detected(self):
        for value in ['192.168.1.10', '10.0.0.2', '172.20.0.5']:
            self.assertTrue(private_ipv4(value))
        for value in ['127.0.0.1', '8.8.8.8', '169.254.0.1', '172.32.0.1', '::1', '*', 'bad']:
            self.assertFalse(private_ipv4(value))
        with patch('hi.management.commands.runlan.socket.gethostbyname_ex', return_value=('host', [], ['192.168.1.10', '127.0.0.1', '192.168.1.10', '8.8.8.8'])):
            self.assertEqual(discover_addresses(), ['192.168.1.10'])
        with patch('hi.management.commands.runlan.socket.gethostbyname_ex', side_effect=OSError):
            self.assertEqual(discover_addresses(), [])

    @override_settings(ALLOWED_HOSTS=['localhost', '127.0.0.1'])
    def test_command_prints_urls_and_binds_on_all_interfaces(self):
        output = io.StringIO()
        with patch('hi.management.commands.runlan.discover_addresses', return_value=['192.168.1.10']), patch('hi.management.commands.runlan.RunserverCommand.handle', return_value=None) as run:
            call_command('runlan', '--noreload', stdout=output)
        self.assertIn('http://192.168.1.10:8000/', output.getvalue())
        self.assertEqual(run.call_args.kwargs['addrport'], '0.0.0.0:8000')
        from django.conf import settings
        self.assertIn('192.168.1.10', settings.ALLOWED_HOSTS)
        self.assertNotIn('*', settings.ALLOWED_HOSTS)

    @override_settings(ALLOWED_HOSTS=['localhost'])
    def test_explicit_ip_custom_port_and_invalid_addresses(self):
        with patch('hi.management.commands.runlan.RunserverCommand.handle', return_value=None) as run:
            call_command('runlan', '--ip', '192.168.2.20', '--port', '8080', stdout=io.StringIO())
            self.assertEqual(run.call_args.kwargs['addrport'], '0.0.0.0:8080')
        for args in [('--ip', '8.8.8.8'), ('--port', '0'), ('--port', '65536')]:
            with self.assertRaises(CommandError):
                call_command('runlan', *args)
        with patch('hi.management.commands.runlan.discover_addresses', return_value=[]), self.assertRaises(CommandError):
            call_command('runlan')

    @override_settings(ALLOWED_HOSTS=['192.168.1.10'])
    def test_forms_support_lan_origin_and_reject_unknown_host(self):
        client = Client(enforce_csrf_checks=True)
        response = client.get(reverse('login'), HTTP_HOST='192.168.1.10:8000')
        self.assertEqual(response.status_code, 200)
        response = client.post(reverse('login'), {'username': 'not_a_user', 'password': 'wrong', 'csrfmiddlewaretoken': client.cookies['csrftoken'].value}, HTTP_HOST='192.168.1.10:8000', HTTP_ORIGIN='http://192.168.1.10:8000')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.get(reverse('login'), HTTP_HOST='evil.example').status_code, 400)
