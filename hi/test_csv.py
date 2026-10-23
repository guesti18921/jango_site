import csv
import io
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .csv_tools import COLUMNS, MAX_BYTES, csv_response, decode_upload, import_csv, parse_csv
from .models import CSVImportJob, MediaContent


class MediaCSVTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('csv_admin', 'admin@example.test', 'Local!Admin528')
        cls.reader = User.objects.create_user('reader', password='Local!Reader528')
        cls.staff = User.objects.create_user('staff', password='Local!Staff528', is_staff=True)
        cls.media = MediaContent.objects.create(title='Исходное название', description='Первая строка\nВторая; с "кавычками"', image='uploads/test.png', author=cls.admin)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.directory.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        path = Path(self.directory.name, 'uploads/test.png')
        path.parent.mkdir()
        path.write_bytes(b'fixture image')
        self.client.force_login(self.admin)

    def text(self, rows=None, delimiter=';', encoding='utf-8-sig'):
        output = io.StringIO(newline='')
        writer = csv.writer(output, delimiter=delimiter)
        writer.writerow(COLUMNS)
        writer.writerows(rows if rows is not None else [['', 'Новое', 'Описание', 'uploads/test.png', 'csv_admin', '1']])
        return output.getvalue().encode(encoding)

    def preview(self, raw=None, **kwargs):
        data = {'file': SimpleUploadedFile('media.csv', raw if raw is not None else self.text()), 'update_existing': 'on', **kwargs}
        return self.client.post(reverse('csv_import'), data)

    def confirm(self, job, client=None):
        return (client or self.client).post(reverse('csv_import'), {'action': 'import', 'job': str(job.pk)})

    def test_export_roundtrip_with_cyrillic_quotes_and_newlines(self):
        response = self.client.get(reverse('csv_export'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b'\xef\xbb\xbf'))
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertIn('no-store', response['Cache-Control'])
        rows = parse_csv(response.content.decode('utf-8-sig'))
        self.assertEqual(rows[0].pk, self.media.pk)
        self.assertEqual(rows[0].description, self.media.description)
        self.assertEqual(rows[0].title, self.media.title)

    def test_preview_does_not_write_and_confirmation_creates(self):
        response = self.preview()
        self.assertContains(response, 'Данные проверены')
        self.assertEqual(MediaContent.objects.count(), 1)
        job = CSVImportJob.objects.get()
        self.assertRedirects(self.confirm(job), reverse('dashboard'))
        self.assertEqual(MediaContent.objects.count(), 2)
        job.refresh_from_db()
        self.assertTrue(job.consumed)
        self.assertEqual(job.csv_text, '')

    def test_existing_id_updates_without_duplicates(self):
        response = self.preview(self.text([[self.media.pk, 'Изменено', 'Описание', 'uploads/test.png', '', 'false']]))
        self.assertContains(response, 'Данные проверены')
        self.confirm(CSVImportJob.objects.get())
        self.assertEqual(MediaContent.objects.count(), 1)
        self.media.refresh_from_db()
        self.assertEqual(self.media.title, 'Изменено')
        self.assertIsNone(self.media.author)
        self.assertFalse(self.media.is_published)

    def test_any_invalid_row_prevents_all_writes(self):
        rows = [['', 'Хорошее', '', 'uploads/test.png', '', '1'], ['', '', '', 'uploads/test.png', '', '1']]
        self.assertContains(self.preview(self.text(rows)), 'Строка 3')
        self.assertFalse(CSVImportJob.objects.exists())
        self.assertEqual(MediaContent.objects.count(), 1)

    def test_missing_image_invalid_author_status_and_id(self):
        for column, value in [(0, '999999'), (0, '-1'), (0, '9' * 100), (3, 'uploads/missing.png'), (4, 'missing'), (5, 'maybe')]:
            with self.subTest(column=column, value=value):
                row = ['', 'Название', '', 'uploads/test.png', '', '1']
                row[column] = value
                self.assertContains(self.preview(self.text([row])), 'Строка 2')
                self.assertFalse(CSVImportJob.objects.exists())

    def test_paths_and_urls_are_rejected(self):
        for image in ['../secret.png', 'uploads/../../secret.png', '/etc/passwd', 'https://example.com/image.png', 'uploads\\test.png']:
            with self.subTest(image=image):
                with self.assertRaises(ValidationError):
                    parse_csv(self.text([['', 'Тест', '', image, '', '1']]).decode('utf-8-sig'))

    def test_duplicate_ids_and_disabled_updates_rejected(self):
        row = [self.media.pk, 'Название', '', 'uploads/test.png', '', '1']
        self.assertContains(self.preview(self.text([row, row])), 'повторяется')
        self.assertContains(self.preview(self.text([row]), update_existing=''), 'включите')

    def test_delimiters_and_windows_encoding(self):
        for delimiter in [';', ',', '\t']:
            raw = self.text(delimiter=delimiter, encoding='cp1251')
            self.assertEqual(len(parse_csv(decode_upload(SimpleUploadedFile('data.csv', raw)))), 1)

    def test_invalid_headers_quotes_empty_and_oversize(self):
        for raw in [b'wrong;header\n1;2', b'', b'\x00data', b'a' * (MAX_BYTES + 1), self.text([]), b'id;title;description;image;author;is_published\n"broken']:
            with self.subTest(size=len(raw)):
                response = self.preview(raw)
                self.assertEqual(response.status_code, 200)
                self.assertFalse(CSVImportJob.objects.exists())
        response = self.client.post(reverse('csv_import'), {'file': SimpleUploadedFile('data.xlsx', b'not csv')})
        self.assertContains(response, 'расширением .csv')

    def test_formula_cells_are_escaped_and_reversible(self):
        for title in ['=1+2', '+cmd', '-cmd', '@SUM(A1)', '\t=1', ' =1', "'literal", "'=literal"]:
            MediaContent.objects.filter(pk=self.media.pk).update(title=title)
            response = self.client.get(reverse('csv_export'))
            text = response.content.decode('utf-8-sig')
            parsed = list(csv.reader(io.StringIO(text), delimiter=';'))
            self.assertTrue(parsed[1][1].startswith("'"))
            self.assertEqual(parse_csv(text)[0].title, title)

    def test_replay_and_other_admin_cannot_apply_preview(self):
        self.preview()
        job = CSVImportJob.objects.get()
        other = User.objects.create_superuser('other_admin', password='Other!Admin528')
        client = Client()
        client.force_login(other)
        self.assertContains(self.confirm(job, client), 'истёк или уже использован')
        self.assertEqual(MediaContent.objects.count(), 1)
        self.confirm(job)
        self.assertContains(self.confirm(job), 'истёк или уже использован')
        self.assertEqual(MediaContent.objects.count(), 2)

    def test_expired_or_invalid_preview_is_rejected(self):
        self.preview()
        job = CSVImportJob.objects.get()
        CSVImportJob.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertContains(self.confirm(job), 'истёк')
        self.assertContains(self.client.post(reverse('csv_import'), {'action': 'import', 'job': 'bad'}), 'Некорректный запрос')
        self.assertEqual(MediaContent.objects.count(), 1)

    def test_changed_data_is_revalidated_on_confirmation(self):
        self.preview()
        Path(self.directory.name, 'uploads/test.png').unlink()
        self.assertContains(self.confirm(CSVImportJob.objects.get()), 'не найден')
        self.assertEqual(MediaContent.objects.count(), 1)
        self.assertFalse(CSVImportJob.objects.get().consumed)

    def test_database_failure_rolls_back_entire_batch(self):
        raw = self.text([['', 'Первое', '', 'uploads/test.png', '', '1'], ['', 'Второе', '', 'uploads/test.png', '', '1']])
        original = MediaContent.save
        calls = []
        def failing_save(obj, *args, **kwargs):
            calls.append(obj.title)
            if len(calls) == 2:
                raise DatabaseError('simulated failure')
            return original(obj, *args, **kwargs)
        with patch.object(MediaContent, 'save', failing_save):
            with self.assertRaises(DatabaseError):
                import_csv(raw.decode('utf-8-sig'))
        self.assertEqual(MediaContent.objects.count(), 1)

    def test_row_limit(self):
        row = ['', 'Название', '', 'uploads/test.png', '', '1']
        with patch('hi.csv_tools.MAX_ROWS', 2):
            self.assertContains(self.preview(self.text([row, row, row])), 'не более 2')

    def test_template_and_empty_export(self):
        response = self.client.get(reverse('csv_import') + '?template=1')
        self.assertEqual(list(csv.reader(io.StringIO(response.content.decode('utf-8-sig')), delimiter=';')), [list(COLUMNS)])
        MediaContent.objects.all().delete()
        self.assertEqual(self.client.get(reverse('csv_export')).content, response.content)

    def test_staff_and_model_permissions_required(self):
        for user in [None, self.reader, self.staff]:
            client = Client()
            if user:
                client.force_login(user)
            for url in ['csv_import', 'csv_export']:
                self.assertEqual(client.get(reverse(url)).status_code, 403 if user == self.staff else 302)
        self.staff.user_permissions.add(Permission.objects.get(codename='view_mediacontent'))
        client = Client()
        client.force_login(self.staff)
        self.assertEqual(client.get(reverse('csv_export')).status_code, 200)
        self.assertEqual(client.get(reverse('csv_import')).status_code, 403)

    def test_csrf_and_admin_links(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.admin)
        self.assertEqual(strict.post(reverse('csv_import'), {'action': 'import', 'job': 'x'}).status_code, 403)
        for url in [reverse('dashboard'), '/django-admin/hi/mediacontent/']:
            self.assertContains(self.client.get(url), reverse('csv_import'))
            self.assertContains(self.client.get(url), reverse('csv_export'))
