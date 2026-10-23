import hashlib
import io
import json
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from .large_uploads import partial_path, upload_lock, UploadBusy
from .models import MediaContent, MediaUpload
from .test_media import audio, animation
from .csv_tools import csv_response, parse_csv
from .upload_views import final_path


class LargeUploadTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.override = override_settings(MEDIA_ROOT=Path(self.temp.name)/'media', MEDIA_UPLOAD_ROOT=Path(self.temp.name)/'staging', MEDIA_CHUNK_BYTES=512, MEDIA_UPLOAD_RESERVE_BYTES=0)
        self.override.enable(); self.addCleanup(self.override.disable)
        self.admin = User.objects.create_superuser('film-admin', password='FilmTest!123')
        self.other = User.objects.create_superuser('other-admin', password='FilmTest!123')
        self.reader = User.objects.create_user('film-reader', password='FilmTest!123')
        self.client.force_login(self.admin)
        self.data = audio()

    def start(self, name='sound.wav', data=None, client=None, **extra):
        data = self.data if data is None else data
        body = {'name':name, 'size':len(data), 'fingerprint':hashlib.sha256(data).hexdigest(), **extra}
        return (client or self.client).post(reverse('upload_start'), json.dumps(body), content_type='application/json')

    def send_all(self, result, data=None):
        data = self.data if data is None else data
        body = result.json()
        for offset in range(body['offset'], len(data), settings.MEDIA_CHUNK_BYTES):
            response = self.client.put(reverse('upload_part', args=[body['id']]), data[offset:offset+settings.MEDIA_CHUNK_BYTES], content_type='application/octet-stream', HTTP_X_UPLOAD_OFFSET=str(offset))
            self.assertEqual(response.status_code, 200, response.content)
        return MediaUpload.objects.get(pk=body['id'])

    def finish(self, item, **metadata):
        return self.client.post(reverse('upload_finish', args=[item.pk]), {'title':'A movie', 'description':'Details', 'is_published':'on', **metadata})

    def test_manifest_accepts_30gb_and_rejects_over_limit_without_allocating_it(self):
        with patch('hi.large_uploads.available_bytes', return_value=100*1024**3):
            response=self.start('movie.mp4', size=30*1024**3)
            self.assertEqual(response.status_code, 201)
            self.assertEqual(partial_path(MediaUpload.objects.get(pk=response.json()['id'])).stat().st_size, 0)
            self.assertEqual(self.start('b.mp4', size=30*1024**3+1).status_code,400)

    def test_resume_duplicate_offset_and_crash_tail(self):
        response = self.start(); identifier=response.json()['id']; url=reverse('upload_part',args=[identifier])
        first=self.client.put(url,self.data[:512], content_type='application/octet-stream',HTTP_X_UPLOAD_OFFSET='0')
        self.assertEqual(first.json()['offset'],512)
        self.assertEqual(self.start().json()['id'],identifier)
        duplicate=self.client.put(url,self.data[:512], content_type='application/octet-stream',HTTP_X_UPLOAD_OFFSET='0')
        self.assertEqual(duplicate.status_code,409)
        self.assertEqual(duplicate.json()['offset'],512)
        item=MediaUpload.objects.get(pk=identifier)
        with partial_path(item).open('ab') as file:file.write(b'UNCOMMITTED TAIL')
        item=self.send_all(self.start())
        self.assertEqual(partial_path(item).read_bytes(),self.data)
        self.assertEqual(item.offset,len(self.data))

    def test_publish_exact_bytes_poster_and_repeat_finish(self):
        item=self.send_all(self.start())
        poster=SimpleUploadedFile('poster.gif',animation(),'image/gif')
        response=self.finish(item,poster=poster)
        self.assertEqual(response.status_code,201,response.content)
        item.refresh_from_db();post=item.post
        self.assertEqual(post.image.read(),self.data)
        self.assertTrue(post.poster)
        self.assertEqual(post.author,self.admin)
        self.assertFalse(partial_path(item).exists())
        self.assertEqual(self.finish(item).status_code,200)
        self.assertEqual(MediaContent.objects.count(),1)
        self.assertEqual(self.client.get('/api/media/').json()['results'][0]['media_kind'],'audio')

    def test_finish_recovers_rename_before_db_commit(self):
        item=self.send_all(self.start());destination=final_path(item);destination.parent.mkdir(parents=True,exist_ok=True)
        partial_path(item).replace(destination)
        self.assertEqual(self.finish(item).status_code,201)
        item.refresh_from_db();self.assertEqual(item.post.image.read(),self.data)

    def test_incomplete_invalid_media_and_bad_metadata_do_not_publish(self):
        item=MediaUpload.objects.get(pk=self.start().json()['id'])
        self.assertEqual(self.finish(item).status_code,409)
        self.send_all(self.start())
        self.assertEqual(self.finish(item,title='').status_code,400)
        bad=b'<html>not a movie</html>'
        invalid=self.send_all(self.start('bad.mp4',bad),bad)
        self.assertEqual(self.finish(invalid).status_code,400)
        self.assertFalse(MediaContent.objects.exists())

    def test_wrong_user_permissions_csrf_and_cancel(self):
        item=MediaUpload.objects.get(pk=self.start().json()['id']);url=reverse('upload_part',args=[item.pk])
        self.client.force_login(self.other)
        for method in ('get','delete'):
            self.assertEqual(getattr(self.client,method)(url).status_code,404)
        self.client.force_login(self.reader)
        self.assertEqual(self.start().status_code,403)
        self.assertEqual(self.client.get(url).status_code,403)
        csrf_client=Client(enforce_csrf_checks=True);csrf_client.force_login(self.admin)
        self.assertEqual(self.start(client=csrf_client).status_code,403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.delete(url).status_code,200)
        self.assertFalse(partial_path(item).exists())
        self.assertNotEqual(self.start().json()['id'],str(item.pk))

    def test_low_disk_reservations_and_chunk_limits(self):
        with patch('hi.large_uploads.available_bytes',return_value=len(self.data)-1):
            self.assertEqual(self.start().status_code,507)
        with patch('hi.large_uploads.available_bytes',return_value=len(self.data)+100):
            response=self.start()
            self.assertEqual(response.status_code,201)
            self.assertEqual(self.start('another.wav').status_code,507)
        url=reverse('upload_part',args=[response.json()['id']])
        self.assertEqual(self.client.put(url,b'x'*513,content_type='application/octet-stream',HTTP_X_UPLOAD_OFFSET='0').status_code,413)
        with patch('hi.upload_views.available_bytes',return_value=1):
            self.assertEqual(self.client.put(url,self.data[:512],content_type='application/octet-stream',HTTP_X_UPLOAD_OFFSET='0').status_code,507)

    def test_expiry_cleanup_and_lock(self):
        item=self.send_all(self.start());item.expires_at=timezone.now()-timedelta(seconds=1);item.save()
        self.assertEqual(self.client.get(reverse('upload_part',args=[item.pk])).status_code,410)
        call_command('cleanupuploads',stdout=io.StringIO())
        self.assertFalse(partial_path(item).exists())
        with upload_lock('testing'):
            with self.assertRaises(UploadBusy):
                with upload_lock('testing'):pass

    def test_invalid_names_and_payloads(self):
        for name in ('../film.mp4',r'C:\film.mp4','bad.html','', 'bad\x00.mp4'):
            self.assertEqual(self.start(name).status_code,400)
        self.assertEqual(self.client.post(reverse('upload_start'),'[]',content_type='application/json').status_code,400)

    def test_local_movie_no_copy_csv_roundtrip_and_draft_permissions(self):
        source=Path(self.temp.name)/'Original.mp4';source.write_bytes(b'\x00\x00\x00\x18ftypisom'+b'x'*80)
        before=source.read_bytes()
        call_command('addfilm',str(source),author=self.admin.username,title='Local movie',draft=True,stdout=io.StringIO())
        post=MediaContent.objects.get(title='Local movie')
        self.assertEqual(post.local_path,str(source.resolve()))
        self.assertFalse(post.image)
        self.assertEqual(MediaContent(local_path=r'D:\Private\Films\movie.mp4').media_name, 'movie.mp4')
        self.assertEqual(source.read_bytes(),before)
        self.assertFalse((Path(settings.MEDIA_ROOT)/'uploads').exists())
        parsed=parse_csv(csv_response(MediaContent.objects.all()).content.decode('utf-8-sig'))
        self.assertEqual(parsed[0].local_path,str(source.resolve()))
        response=self.client.get(reverse('media_stream',args=[post.pk]),HTTP_RANGE='bytes=4-7')
        self.assertEqual(b''.join(response.streaming_content),b'ftyp')
        self.client.force_login(self.reader)
        self.assertEqual(self.client.get(reverse('media_stream',args=[post.pk])).status_code,404)
        post.is_published=True;post.save()
        self.assertEqual(self.client.get(reverse('media_stream',args=[post.pk])).status_code,200)
        source.unlink()
        self.assertEqual(self.client.get(reverse('media_stream',args=[post.pk])).status_code,404)

    def test_existing_movie_command_rejects_invalid_source_and_author(self):
        source=Path(self.temp.name)/'fake.mp4';source.write_bytes(b'not a video')
        with self.assertRaises(CommandError):call_command('addfilm',str(source),author=self.admin.username,stdout=io.StringIO())
        with self.assertRaises(CommandError):call_command('addfilm',str(source),author=self.reader.username,stdout=io.StringIO())

    def test_byte_ranges_suffix_head_invalid_and_large_seek(self):
        item=self.send_all(self.start());self.finish(item);item.refresh_from_db();url=reverse('media_stream',args=[item.post_id])
        for header,expected in [('bytes=0-3',self.data[:4]),('bytes=4-',self.data[4:]),('bytes=-8',self.data[-8:])]:
            response=self.client.get(url,HTTP_RANGE=header)
            self.assertEqual(response.status_code,206)
            self.assertEqual(b''.join(response.streaming_content),expected)
            self.assertEqual(response['Accept-Ranges'],'bytes')
        response=self.client.head(url,HTTP_RANGE='bytes=4-7')
        self.assertEqual(response.status_code,206);self.assertEqual(response['Content-Length'],'4')
        self.assertEqual(response.content,b'')
        for header in ('bytes=9999999-','bytes=8-2','bytes=-0','bytes=0-1,4-5','nonsense'):
            self.assertEqual(self.client.get(url,HTTP_RANGE=header).status_code,416)
        # Sparse file: exercise >32-bit offsets without allocating a multi-GB fixture.
        source=Path(self.temp.name)/'large.mp4'
        with source.open('wb') as file:file.seek(3*1024**3);file.write(b'END')
        post=MediaContent.objects.create(title='Large seek',local_path=str(source))
        response=self.client.get(reverse('media_stream',args=[post.pk]),HTTP_RANGE='bytes=-3')
        self.assertEqual(b''.join(response.streaming_content),b'END')
        self.assertEqual(response['Content-Length'],'3')
