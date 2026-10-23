import io
import tempfile
import wave
from PIL import Image
from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from .forms import MediaContentAdminForm
from .models import MediaContent, Comment
from .csv_tools import csv_response, parse_csv


def animation():
    output = io.BytesIO()
    frames = [Image.new('RGB', (8, 8), color) for color in ('red', 'blue')]
    frames[0].save(output, format='GIF', save_all=True, append_images=frames[1:], duration=200, loop=0)
    return output.getvalue()


def audio():
    output = io.BytesIO()
    with wave.open(output, 'wb') as file:
        file.setnchannels(1); file.setsampwidth(2); file.setframerate(8000)
        file.writeframes(b'\0\0' * 800)
    return output.getvalue()


class MediaTests(TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.settings = override_settings(MEDIA_ROOT=self.folder.name)
        self.settings.enable(); self.addCleanup(self.settings.disable)
        self.admin = User.objects.create_superuser('creator', password='Media!Test123')
        self.client.force_login(self.admin)

    def form(self, upload, instance=None):
        return MediaContentAdminForm({'title': 'Uploaded media', 'description': 'Test', 'is_published': True}, {'image': upload}, instance=instance)

    def test_animated_upload_survives_without_flattening(self):
        data = animation()
        form = self.form(SimpleUploadedFile('animated.gif', data, 'image/gif'))
        self.assertTrue(form.is_valid(), form.errors)
        post = form.save()
        with post.image.open('rb') as file:
            self.assertEqual(file.read(), data)
        with Image.open(post.image.path) as image:
            self.assertEqual(image.n_frames, 2)
        self.assertContains(self.client.get(reverse('post_detail', args=[post.pk])), post.image.url)

    def test_audio_admin_upload_feed_player_api_and_csv(self):
        response = self.client.post(reverse('admin:hi_mediacontent_add'), {
            'title': 'Audio test', 'description': 'Sound', 'is_published': 'on',
            'image': SimpleUploadedFile('sound.wav', audio(), 'audio/wav'), '_save': 'Save',
        })
        self.assertEqual(response.status_code, 302)
        post = MediaContent.objects.get(title='Audio test')
        self.assertEqual(post.author, self.admin)
        for url in (reverse('home'), reverse('post_detail', args=[post.pk])):
            self.assertContains(self.client.get(url), '<audio controls')
        api = self.client.get('/api/media/').json()['results'][0]
        self.assertEqual(api['media_kind'], 'audio')
        self.assertEqual(api['media_mime'], 'audio/wav')
        self.assertIn(f'/files/{post.pk}/', api['image'])
        parsed = parse_csv(csv_response(MediaContent.objects.filter(pk=post.pk)).content.decode('utf-8-sig'))
        self.assertEqual(parsed[0].image.name, post.image.name)
        edit = MediaContentAdminForm({'title': 'Renamed', 'description': '', 'is_published': True}, instance=post)
        self.assertTrue(edit.is_valid(), edit.errors)

    def test_video_player_and_download_for_unsupported_image(self):
        post = MediaContent.objects.create(title='Video', image='uploads/clip.mp4')
        self.assertContains(self.client.get(reverse('post_detail', args=[post.pk])), '<video controls')
        post.image = 'uploads/photo.heic'; post.save()
        response = self.client.get(reverse('post_detail', args=[post.pk]))
        self.assertContains(response, 'download')
        self.assertNotContains(response, '<img class="post-media-image"')

    def test_wrong_type_and_oversized_upload_are_rejected(self):
        for name in ('fake.mp4', 'fake.png', 'fake.mp3', 'fake.svg', 'fake.html'):
            with self.subTest(name=name):
                self.assertFalse(self.form(SimpleUploadedFile(name, b'<html>not media</html>')).is_valid())
        upload = SimpleUploadedFile('sound.wav', audio(), 'audio/wav')
        upload.size = 100 * 1024 * 1024 + 1
        self.assertFalse(self.form(upload).is_valid())

    def test_profile_avatar_in_comments_and_management(self):
        response = self.client.post(reverse('profile_edit'), {
            'first_name': '', 'last_name': '', 'email': 'creator@example.com',
            'bio': '', 'city': '', 'birth_date': '',
            'avatar': SimpleUploadedFile('avatar.gif', animation(), 'image/gif'),
        })
        self.assertEqual(response.status_code, 302)
        self.admin.profile.refresh_from_db()
        url = self.admin.profile.avatar.url
        post = MediaContent.objects.create(title='Avatar post', image='uploads/test.jpg')
        Comment.objects.create(post=post, user=self.admin, text='My avatar')
        response = self.client.get(reverse('post_detail', args=[post.pk]))
        self.assertContains(response, f'class="comment-avatar" src="{url}"')
        self.assertContains(self.client.get(reverse('dashboard')+'?section=comments'), f'class="avatar-letter small" src="{url}"')
        self.assertContains(self.client.get(reverse('dashboard')+'?section=users'), url)
        self.assertContains(self.client.get(reverse('profile')), url)
