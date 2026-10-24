from django.test import TestCase
from django.contrib.auth.models import User, Permission
from django.urls import reverse
from .models import MediaContent, Comment


class DashboardTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('manager', password='test-pass')
        self.member = User.objects.create_user('member', password='test-pass')
        self.published = MediaContent.objects.create(title='Landscape', is_published=True)
        self.draft = MediaContent.objects.create(title='Secret draft', is_published=False)
        Comment.objects.create(post=self.published, user=self.member, text='Great photograph')

    def test_search_filter_and_live_counts(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('dashboard'), {'status': 'draft', 'q': 'Secret'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['media_page']), [self.draft])
        self.assertEqual(response.context['total_media'], 2)
        self.assertEqual(response.context['total_comments'], 1)
        self.assertContains(response, 'Great photograph')
        self.assertNotContains(response, '>Landscape</strong>')

    def test_language_and_authorless_posts(self):
        self.client.force_login(self.admin)
        self.client.cookies['django_language'] = 'en'
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Overview')
        self.assertContains(response, 'Landscape')

    def test_member_cannot_access_dashboard(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 302)

    def test_staff_without_permissions_sees_no_private_data(self):
        self.member.is_staff = True
        self.member.save()
        self.client.force_login(self.member)
        response = self.client.get(reverse('dashboard'))
        self.assertNotContains(response, 'Secret draft')
        self.assertNotContains(response, 'Great photograph')
        self.assertEqual(self.client.post(reverse('dashboard'), {'action': 'draft', 'selected': self.published.pk}).status_code, 403)

    def test_publish_action_keeps_permissions_and_audit_log(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('dashboard'), {'action': 'publish', 'selected': self.draft.pk})
        self.assertEqual(response.status_code, 302)
        self.draft.refresh_from_db()
        self.assertTrue(self.draft.is_published)
        self.assertTrue(self.admin.logentry_set.filter(object_id=str(self.draft.pk)).exists())

    def test_sections_grid_and_native_editors(self):
        self.client.force_login(self.admin)
        for language in ('ru', 'en'):
            self.client.cookies['django_language'] = language
            for path in ('/dashboard/?section=posts&layout=grid', '/dashboard/?section=comments', '/dashboard/?section=users', '/django-admin/', '/django-admin/hi/', '/django-admin/hi/mediacontent/add/', f'/django-admin/hi/mediacontent/{self.published.pk}/change/', '/django-admin/auth/user/'):
                with self.subTest(language=language, path=path):
                    self.assertEqual(self.client.get(path).status_code, 200)
        self.assertContains(self.client.get('/dashboard/?layout=grid'), 'management-grid')

    def test_filters_pagination_and_search_keep_state(self):
        self.client.force_login(self.admin)
        MediaContent.objects.bulk_create([MediaContent(title=f'Paged draft {i}', is_published=False) for i in range(15)])
        response = self.client.get('/dashboard/?section=posts&q=Paged&status=draft&layout=grid&page=2')
        self.assertEqual(len(response.context['page']), 3)
        self.assertEqual(response.context['page'].paginator.count, 15)
        self.assertIn('status=draft', response.context['page_query'])
        self.assertNotIn('page=', response.context['page_query'])
        self.assertNotIn('status=', response.context['tab_query'])
        self.assertEqual(self.client.get('/dashboard/?page=invalid').status_code, 200)
        self.assertContains(self.client.get('/dashboard/?q=unknown-xyz'), 'Ничего не найдено.')

    def test_readonly_staff_cannot_mutate_and_restricted_sections_are_denied(self):
        self.member.is_staff = True
        self.member.save()
        self.member.user_permissions.add(Permission.objects.get(codename='view_mediacontent'))
        self.client.force_login(self.member)
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Secret draft')
        self.assertNotContains(response, 'name="selected"')
        self.assertNotContains(response, 'Great photograph')
        for section in ('users', 'comments'):
            self.assertEqual(self.client.get('/dashboard/?section='+section).status_code, 403)
        for data in ({'action':'publish','selected':self.draft.pk}, {'action':'delete_comment','comment_id':Comment.objects.get().pk}):
            self.assertEqual(self.client.post(reverse('dashboard'), data).status_code, 403)
        self.assertFalse(MediaContent.objects.get(pk=self.draft.pk).is_published)
        self.assertEqual(Comment.objects.count(), 1)

    def test_bulk_changes_and_comment_delete_are_logged(self):
        self.client.force_login(self.admin)
        self.client.post('/dashboard/?section=posts&status=published', {'action':'draft','selected':[self.published.pk, self.draft.pk]})
        self.assertFalse(MediaContent.objects.filter(is_published=True).exists())
        comment = Comment.objects.get()
        response = self.client.post('/dashboard/?section=comments', {'action':'delete_comment','comment_id':comment.pk})
        self.assertEqual(response['Location'], '/dashboard/?section=comments')
        self.assertFalse(Comment.objects.exists())
        self.assertEqual(self.admin.logentry_set.count(), 3)
        self.assertEqual(self.client.post('/dashboard/', {'action':'delete_comment','comment_id':'invalid'}).status_code, 400)
        response = self.client.post('/dashboard/', {'action':'publish','selected':'9'*30})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(MediaContent.objects.filter(is_published=True).exists())

    def test_post_actions_require_csrf(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        response = client.post(reverse('dashboard'), {'action':'publish','selected':self.draft.pk})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(MediaContent.objects.get(pk=self.draft.pk).is_published)

    def test_native_post_create_and_edit_still_save_author_and_content(self):
        import io
        from PIL import Image
        from tempfile import TemporaryDirectory
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings
        self.client.force_login(self.admin)
        buffer = io.BytesIO()
        Image.new('RGB', (8, 8), color='green').save(buffer, format='PNG')
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            response = self.client.post(reverse('admin:hi_mediacontent_add'), {
                'title':'Added through editor', 'description':'Original description',
                'image':SimpleUploadedFile('editor.png',buffer.getvalue(),content_type='image/png'),
                'is_published':'on', '_save':'Save',
            })
            self.assertEqual(response.status_code, 302)
            post = MediaContent.objects.get(title='Added through editor')
            self.assertEqual(post.author, self.admin)
            response = self.client.post(reverse('admin:hi_mediacontent_change',args=[post.pk]), {
                'title':'Edited through editor', 'description':'Updated description', '_save':'Save',
            })
            self.assertEqual(response.status_code, 302)
            post.refresh_from_db()
            self.assertEqual(post.title, 'Edited through editor')
            self.assertEqual(post.description, 'Updated description')
            self.assertFalse(post.is_published)
            self.assertEqual(post.author, self.admin)

class NativeAdminNavigationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_superuser('nav-owner', password='AdminNav!823')
        cls.reader = User.objects.create_user('nav-reader', password='AdminNav!823', is_staff=True)
        cls.reader.user_permissions.add(Permission.objects.get(codename='view_mediacontent'))
        cls.uploader = User.objects.create_user('nav-uploader', password='AdminNav!823', is_staff=True)
        cls.uploader.user_permissions.add(Permission.objects.get(codename='add_mediacontent'))

    def test_primary_order_and_existing_additional_sections_in_both_languages(self):
        self.client.force_login(self.owner)
        for language in ('ru', 'en'):
            self.client.cookies['django_language'] = language
            for url in (reverse('admin:index'), reverse('admin:app_list', args=['hi'])):
                response = self.client.get(url)
                self.assertEqual([m['key'] for m in response.context['gallery_primary']],
                                 ['hi.mediacontent', 'hi.comment', 'auth.user'])
                self.assertEqual(len(response.context['gallery_additional']), 10)
                self.assertContains(response, 'class="gallery-admin-panel gallery-admin-additional"')
                self.assertContains(response, reverse('upload_page'))
                self.assertNotContains(response, 'Медиа контент')
                self.assertNotContains(response, 'Media content')
        # Grouping navigation does not remove or redirect original model screens.
        for name in ('company', 'developer', 'skill', 'historyitem'):
            self.assertEqual(self.client.get(reverse(f'admin:hi_{name}_changelist')).status_code, 200)

    def test_readonly_staff_has_no_upload_or_unrelated_models(self):
        self.client.force_login(self.reader)
        for url in (reverse('admin:index'), reverse('admin:app_list', args=['hi'])):
            response = self.client.get(url)
            self.assertEqual([m['key'] for m in response.context['gallery_primary']], ['hi.mediacontent'])
            self.assertFalse(response.context['gallery_can_upload'])
            self.assertEqual(response.context['gallery_additional'], [])
            self.assertNotContains(response, reverse('upload_page'))
            self.assertNotContains(response, reverse('admin:auth_user_changelist'))
        self.assertEqual(self.client.get(reverse('admin:hi_company_changelist')).status_code, 403)
        for model in ('company', 'developer'):
            self.assertEqual(self.client.get(reverse(f'admin:hi_{model}_add')).status_code, 403)
        self.assertEqual(self.client.get(reverse('upload_page')).status_code, 302)
        # Staff managing accounts alone can still use the global start page.
        self.reader.user_permissions.set([Permission.objects.get(codename='view_user')])
        response = self.client.get(reverse('admin:index'))
        self.assertEqual([m['key'] for m in response.context['gallery_primary']], ['auth.user'])
        self.assertFalse(response.context['gallery_can_upload'])
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)

    def test_add_only_staff_gets_existing_upload_and_form_without_list_access(self):
        self.client.force_login(self.uploader)
        response = self.client.get(reverse('admin:index'))
        self.assertContains(response, reverse('upload_page'))
        primary = response.context['gallery_primary']
        self.assertEqual([m['key'] for m in primary], ['hi.mediacontent'])
        self.assertIsNone(primary[0]['admin_url'])
        self.assertEqual(primary[0]['add_url'], reverse('admin:hi_mediacontent_add'))
        self.assertEqual(self.client.get(reverse('admin:hi_mediacontent_add')).status_code, 200)
        self.assertEqual(self.client.get(reverse('admin:hi_mediacontent_changelist')).status_code, 403)
