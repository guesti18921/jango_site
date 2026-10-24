import io
import re
from contextlib import redirect_stdout

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from .models import Comment, MediaContent, Rating


class BilingualDesignTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser('design_admin', 'design@example.test', 'Design!Local872')
        cls.post = MediaContent.objects.create(title='Пост автора на русском', description='Этот текст нельзя переводить автоматически.', image='uploads/design.jpg', author=cls.user)
        cls.comment = Comment.objects.create(post=cls.post, user=cls.user, text='Комментарий на языке автора')

    def test_language_switch_cookie_and_return_to_current_page(self):
        self.client.force_login(self.user)
        page = reverse('post_detail', args=[self.post.pk])
        response = self.client.post(reverse('set_language'), {'language': 'en', 'next': page})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], page)
        self.assertEqual(response.cookies['django_language'].value, 'en')
        english = self.client.get(page)
        self.assertContains(english, '<html lang="en">')
        self.assertContains(english, 'Post comment')
        self.assertContains(english, 'Your rating')
        self.assertContains(english, self.post.title)
        self.assertContains(english, self.post.description)
        self.assertContains(english, self.comment.text)
        self.client.post(reverse('set_language'), {'language': 'ru', 'next': page})
        self.assertContains(self.client.get(page), 'Оставить комментарий')
        self.assertEqual(self.client.cookies['django_language'].value, 'ru')

    def test_accept_language_and_cookie_precedence(self):
        self.assertContains(self.client.get(reverse('login'), HTTP_ACCEPT_LANGUAGE='en-US,en;q=0.9'), 'Good to see you')
        self.client.cookies['django_language'] = 'ru'
        self.assertContains(self.client.get(reverse('login'), HTTP_ACCEPT_LANGUAGE='en'), 'Рады вас видеть')

    def test_auth_forms_and_errors_in_english(self):
        self.client.cookies['django_language'] = 'en'
        for name in ['login', 'register', 'staff-login', 'recovery_request']:
            self.assertContains(self.client.get(reverse(name)), '<html lang="en">')
        response = self.client.post(reverse('login'), {'username': 'design_admin', 'password': 'wrong'})
        self.assertContains(response, 'Please enter a correct username and password')
        self.assertContains(self.client.get(reverse('recovery_request')), 'Username or email')

    def test_all_main_admin_and_csv_pages_in_both_languages(self):
        self.client.force_login(self.user)
        for language in ['ru', 'en']:
            self.client.cookies['django_language'] = language
            for url in ['/', '/profile/', '/profile/edit/', '/dashboard/', '/dashboard/csv/import/', '/app/', '/api-test/', '/django-admin/', '/django-admin/hi/mediacontent/', '/django-admin/hi/comment/']:
                with self.subTest(language=language, url=url):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, 'name="language"')
            response = self.client.get('/dashboard/csv/import/')
            self.assertContains(response, 'Update existing records by ID' if language == 'en' else 'Обновлять существующие записи по ID')

    def test_english_comment_validation_and_rating(self):
        self.client.force_login(self.user)
        self.client.cookies['django_language'] = 'en'
        response = self.client.post(reverse('add_comment', args=[self.post.pk]), {'text': ' '})
        self.assertContains(response, 'This field is required.', status_code=400)
        self.assertContains(response, 'name="next" value="/posts/', status_code=400)
        self.assertNotContains(response, 'name="next" value="/posts/'+str(self.post.pk)+'/comment/', status_code=400)
        self.client.post(reverse('rate_post', args=[self.post.pk]), {'value': 5})
        self.assertEqual(Rating.objects.get().value, 5)
        self.assertContains(self.client.get(reverse('post_detail', args=[self.post.pk])), 'Your rating has been saved.')

    def test_recovery_english_form_and_console_code(self):
        self.client.cookies['django_language'] = 'en'
        output = io.StringIO()
        with redirect_stdout(output):
            response = self.client.post(reverse('recovery_request'), {'identifier': 'design_admin'})
        self.assertEqual(response.status_code, 302)
        code = re.search(r'Code: ([0-9]{6})', output.getvalue()).group(1)
        self.assertContains(self.client.get(reverse('recovery_confirm')), 'Confirmation code')
        response = self.client.post(reverse('recovery_confirm'), {'code':code,'new_password1':'Fresh!Design983','new_password2':'Fresh!Design983'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.client.login(username='design_admin', password='Fresh!Design983'))

    def test_language_switch_protects_csrf_and_external_redirects(self):
        strict=Client(enforce_csrf_checks=True)
        self.assertEqual(strict.post(reverse('set_language'), {'language':'en','next':'/'}).status_code,403)
        response=self.client.post(reverse('set_language'), {'language':'en','next':'https://evil.example/'})
        self.assertNotIn('evil.example',response['Location'])
        self.client.post(reverse('set_language'), {'language':'xx','next':'/'})
        self.assertEqual(self.client.cookies['django_language'].value,'en')

    def test_js_catalog_and_api_metadata(self):
        self.client.cookies['django_language']='en'
        self.assertContains(self.client.get(reverse('javascript-catalog')), 'Comments and ratings')
        Rating.objects.create(post=self.post,user=self.user,value=4)
        response=self.client.get('/api/media/')
        row=response.json()['results'][0]
        self.assertEqual((row['average_rating'],row['rating_count'],row['comment_count']),(4.0,1,1))
        self.assertEqual(row['title'],self.post.title)

    def test_default_without_js_has_standard_forms_and_post_links(self):
        self.client.force_login(self.user)
        response=self.client.get('/')
        self.assertContains(response, reverse('post_detail', args=[self.post.pk]))
        self.assertContains(response, 'action="/i18n/setlang/"')
        self.assertContains(response, 'csrfmiddlewaretoken')
        self.assertContains(response, 'class="mobile-nav"')

    def test_posts_without_author_render_for_staff_and_regular_users(self):
        post = MediaContent.objects.create(
            title='Материал без автора', image='uploads/legacy.jpg',
            author=None, is_published=True,
        )
        reader = User.objects.create_user('reader', password='Reader!Local872')
        for account in [self.user, reader]:
            self.client.force_login(account)
            for language in ['ru', 'en']:
                self.client.cookies['django_language'] = language
                with self.subTest(account=account.username, language=language):
                    self.assertContains(self.client.get('/'), post.title)
                    self.assertContains(self.client.get('/'), 'VEYRA')
                    self.assertContains(
                        self.client.get(reverse('post_detail', args=[post.pk])),
                        post.title,
                    )
