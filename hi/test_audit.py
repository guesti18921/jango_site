import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
from django.conf import settings
from django.contrib.auth.models import User, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import OperationalError, connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from .forms import ProfileForm
from .large_uploads import partial_path, upload_lock
from .media_queries import with_engagement
from .models import Comment, MediaContent, MediaUpload, Rating
from .test_media import animation, audio


class AuditTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.override=override_settings(MEDIA_ROOT=Path(self.temp.name)/'media', MEDIA_UPLOAD_ROOT=Path(self.temp.name)/'staging', MEDIA_CHUNK_BYTES=512, MEDIA_UPLOAD_RESERVE_BYTES=0)
        self.override.enable();self.addCleanup(self.override.disable)
        self.admin=User.objects.create_superuser('audit-admin',password='Audit!Local123')
        self.reader=User.objects.create_user('audit-reader',password='Audit!Local123')
        self.staff=User.objects.create_user('audit-staff',password='Audit!Local123',is_staff=True)
        self.post=MediaContent.objects.create(title='Public photo',image='uploads/public.gif')
        self.draft=MediaContent.objects.create(title='Private photo',image='uploads/private.gif',poster='posters/private.gif',is_published=False)
        for name in ('uploads/public.gif','uploads/private.gif','posters/private.gif'):
            path=Path(self.temp.name)/'media'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(animation())

    def test_direct_draft_image_and_poster_are_protected_including_debug(self):
        for user in (None,self.reader,self.staff):
            self.client.logout()
            if user:self.client.force_login(user)
            for path in ('/media/uploads/private.gif','/media/posters/private.gif',reverse('media_stream',args=[self.draft.pk])):
                self.assertEqual(self.client.get(path).status_code,404)
            response=self.client.get('/media/uploads/public.gif')
            self.assertEqual(response.status_code,200);response.close()
        self.staff.user_permissions.add(Permission.objects.get(codename='view_mediacontent'))
        self.client.force_login(self.staff)
        for path in ('/media/uploads/private.gif','/media/posters/private.gif'):
            response=self.client.get(path);self.assertEqual(response.status_code,200);response.close()

    def test_staff_without_view_permission_does_not_see_drafts(self):
        self.client.force_login(self.staff)
        self.assertNotContains(self.client.get('/'),self.draft.title)
        self.assertEqual(self.client.get(reverse('post_detail',args=[self.draft.pk])).status_code,404)
        self.assertEqual(self.client.post(reverse('add_comment',args=[self.draft.pk]),{'text':'Hidden'}).status_code,404)
        self.assertEqual(self.client.get('/api/media/'+str(self.draft.pk)+'/').status_code,404)

    def test_raw_unregistered_file_is_not_public(self):
        path=Path(self.temp.name)/'media'/'uploads'/'unregistered.gif';path.write_bytes(animation())
        self.assertEqual(self.client.get('/media/uploads/unregistered.gif').status_code,404)
        self.assertEqual(self.client.get('/media/../db.sqlite3').status_code,404)

    def test_shared_public_image_remains_available(self):
        self.post.image=self.draft.image;self.post.save()
        response=self.client.get('/media/uploads/private.gif')
        self.assertEqual(response.status_code,200);response.close()

    def test_avatar_media_is_still_visible(self):
        self.reader.profile.avatar.save('avatar.gif',SimpleUploadedFile('avatar.gif',animation()),save=True)
        response=self.client.get(self.reader.profile.avatar.url)
        self.assertEqual(response.status_code,200);response.close()

    def test_logout_requires_post_and_csrf(self):
        self.client.force_login(self.reader)
        self.assertEqual(self.client.get(reverse('logout')).status_code,405)
        self.assertIn('_auth_user_id',self.client.session)
        strict=Client(enforce_csrf_checks=True);strict.force_login(self.reader)
        self.assertEqual(strict.post(reverse('logout')).status_code,403)
        self.assertEqual(self.client.post(reverse('logout')).status_code,302)
        self.assertNotIn('_auth_user_id',self.client.session)

    def test_login_returns_to_post_but_rejects_external_next(self):
        target=reverse('post_detail',args=[self.post.pk])
        self.assertEqual(self.client.post(reverse('login'),{'username':self.reader.username,'password':'Audit!Local123','next':target})['Location'],target)
        for target in ('https://outside.example/','//outside.example/','javascript:alert(1)'):
            self.client.logout()
            response=self.client.post(reverse('login'),{'username':self.reader.username,'password':'Audit!Local123','next':target})
            self.assertEqual(response['Location'],'/')

    def test_feed_is_bounded_and_second_page_reachable(self):
        MediaContent.objects.bulk_create([MediaContent(title=f'Photo {i}',image='uploads/public.gif') for i in range(22)])
        self.client.force_login(self.reader)
        page=self.client.get('/')
        self.assertEqual(len(page.context['all_media']),18)
        self.assertContains(page,'?page=2')
        self.assertEqual(len(self.client.get('/?page=2').context['all_media']),5)
        self.assertEqual(self.client.get('/?page=invalid').status_code,200)

    def test_query_count_does_not_grow_with_cards_and_summaries_are_correct(self):
        Rating.objects.create(post=self.post,user=self.reader,value=2)
        Rating.objects.create(post=self.post,user=self.admin,value=5)
        Comment.objects.bulk_create([Comment(post=self.post,user=self.reader,text='Note') for _ in range(100)])
        row=with_engagement(MediaContent.objects.all()).get(pk=self.post.pk)
        self.assertEqual((row.average_rating,row.rating_count,row.comment_count),(3.5,2,100))
        self.client.force_login(self.reader)
        with CaptureQueriesContext(connection) as small:self.client.get('/')
        MediaContent.objects.bulk_create([MediaContent(title=f'Another {i}',image='uploads/public.gif',author=self.admin) for i in range(16)])
        with CaptureQueriesContext(connection) as many:self.client.get('/')
        self.assertLessEqual(len(many),len(small)+1)

    def test_feed_defers_media_and_marks_only_uncovered_videos_for_preview(self):
        video=MediaContent.objects.create(title='Video',image='uploads/movie.mp4')
        MediaContent.objects.create(title='Covered video',image='uploads/covered.mp4',poster='posters/cover.jpg')
        MediaContent.objects.create(title='Audio',image='uploads/sound.wav')
        self.client.force_login(self.reader)
        response=self.client.get('/')
        self.assertContains(response,'preload="none"',count=3)
        self.assertContains(response,'data-video-preview',count=1)
        self.assertContains(self.client.get(reverse('post_detail',args=[video.pk])),'data-video-preview',count=1)
        self.assertNotContains(response,'preload="metadata"')
        self.assertContains(self.client.get(reverse('post_detail',args=[self.post.pk])),'post-detail--image')

    def test_oversized_avatar_rejected(self):
        upload=SimpleUploadedFile('avatar.gif',animation(),'image/gif');upload.size=10*1024**2+1
        form=ProfileForm({'city':'','bio':'','birth_date':''},{'avatar':upload},instance=self.reader.profile)
        self.assertFalse(form.is_valid());self.assertIn('avatar',form.errors)

    @override_settings(DEBUG=False)
    def test_missing_pages_and_csrf_errors_have_readable_pages(self):
        response=self.client.get('/not-a-page/')
        self.assertEqual(response.status_code,404)
        self.assertContains(response,'Здесь пока ничего нет',status_code=404)
        self.assertNotContains(response,'Traceback',status_code=404)
        strict=Client(enforce_csrf_checks=True)
        self.assertContains(strict.post(reverse('logout')),'Нет доступа',status_code=403)

    def completed_upload(self):
        self.client.force_login(self.admin)
        import hashlib,json
        data=audio();manifest=self.client.post(reverse('upload_start'),json.dumps({'name':'audit.wav','size':len(data),'fingerprint':hashlib.sha256(data).hexdigest()}),content_type='application/json').json()
        for offset in range(0,len(data),512):
            response=self.client.put(reverse('upload_part',args=[manifest['id']]),data[offset:offset+512],content_type='application/octet-stream',HTTP_X_UPLOAD_OFFSET=str(offset))
            self.assertEqual(response.status_code,200)
        return MediaUpload.objects.get(pk=manifest['id'])

    def test_failed_final_transaction_preserves_bytes_and_retry_is_idempotent(self):
        item=self.completed_upload();body={'title':'Retry post','is_published':'on'}
        with patch.object(MediaUpload,'save',side_effect=OperationalError('locked')):
            response=self.client.post(reverse('upload_finish',args=[item.pk]),body)
        self.assertEqual(response.status_code,503)
        self.assertEqual(partial_path(item).read_bytes(),audio())
        self.assertFalse(MediaContent.objects.filter(title='Retry post').exists())
        self.assertEqual(self.client.post(reverse('upload_finish',args=[item.pk]),body).status_code,201)
        # A retried request need not carry valid metadata once completion was committed.
        self.assertEqual(self.client.post(reverse('upload_finish',args=[item.pk]),{'title':''}).status_code,200)
        self.assertEqual(MediaContent.objects.filter(title='Retry post').count(),1)

    def test_chunk_csrf_and_completed_cancel_are_rejected(self):
        item=self.completed_upload()
        strict=Client(enforce_csrf_checks=True);strict.force_login(self.admin)
        self.assertEqual(strict.put(reverse('upload_part',args=[item.pk]),b'data',content_type='application/octet-stream').status_code,403)
        self.client.post(reverse('upload_finish',args=[item.pk]),{'title':'Finished'})
        self.assertEqual(self.client.delete(reverse('upload_part',args=[item.pk])).status_code,409)
        item.refresh_from_db();self.assertTrue(item.post.image.storage.exists(item.post.image.name))

    def test_os_lock_is_released_after_process_crash(self):
        if os.name!='posix':self.skipTest('Process crash probe uses Unix flock; Windows uses msvcrt locking.')
        from .large_uploads import root
        path=str(root()/'crash.lock')
        program="import fcntl,sys,time;f=open(sys.argv[1],'a+b');fcntl.flock(f,fcntl.LOCK_EX);print('locked',flush=True);time.sleep(30)"
        process=subprocess.Popen([sys.executable,'-c',program,path],stdout=subprocess.PIPE,text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(),'locked')
            process.kill();process.wait(timeout=5)
            with upload_lock('crash'):pass
        finally:
            if process.poll() is None:process.kill();process.wait(timeout=5)
            process.stdout.close()


    def test_delete_frees_owned_movie_but_preserves_external_and_shared_files(self):
        item=self.completed_upload()
        self.client.post(reverse('upload_finish',args=[item.pk]),{'title':'Managed media','is_published':'on'})
        item.refresh_from_db();post=item.post;name=post.image.name;storage=post.image.storage
        shared=MediaContent.objects.create(title='Shared reference',image=name)
        with self.captureOnCommitCallbacks(execute=True):post.delete()
        self.assertTrue(storage.exists(name))
        with self.captureOnCommitCallbacks(execute=True):shared.delete()
        self.assertFalse(storage.exists(name))
        original=Path(self.temp.name)/'original.mp4';original.write_bytes(b'original source')
        linked=MediaContent.objects.create(title='Original external',local_path=str(original))
        with self.captureOnCommitCallbacks(execute=True):linked.delete()
        self.assertTrue(original.exists())

    def test_rolled_back_deletion_never_removes_movie_bytes(self):
        from django.db import transaction
        item=self.completed_upload();self.client.post(reverse('upload_finish',args=[item.pk]),{'title':'Rollback media'})
        item.refresh_from_db();post=item.post;name=post.image.name;storage=post.image.storage
        with self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    post.delete()
                    raise RuntimeError('rollback')
            except RuntimeError:
                pass
        self.assertTrue(storage.exists(name))
        self.assertTrue(MediaContent.objects.filter(title='Rollback media').exists())


    def test_large_form_is_rejected_without_reading_the_body(self):
        from django.test import RequestFactory
        from .upload_limits import UploadBodyLimitMiddleware
        def unexpected(request):
            self.fail('Oversized request reached body parsing')
        middleware=UploadBodyLimitMiddleware(unexpected)
        for url,size in [('/profile/edit/',13*1024**2),('/dashboard/uploads/start/',9000),('/dashboard/uploads/session/test/',settings.MEDIA_CHUNK_BYTES+1),('/django-admin/hi/mediacontent/add/',113*1024**2)]:
            request=RequestFactory().generic('PUT' if '/session/' in url else 'POST',url,b'',CONTENT_LENGTH=str(size))
            response=middleware(request)
            self.assertEqual(response.status_code,413)
            self.assertFalse(request._read_started)


    def test_native_moderation_and_fk_choices_do_not_expose_drafts(self):
        comment=Comment.objects.create(post=self.draft,user=self.reader,text='Private discussion')
        rating=Rating.objects.create(post=self.draft,user=self.reader,value=5)
        self.staff.user_permissions.add(*Permission.objects.filter(codename__in=['view_comment','change_comment','add_comment','view_rating','change_rating','add_rating']))
        self.client.force_login(self.staff)
        for model,pk in [('comment',comment.pk),('rating',rating.pk)]:
            response=self.client.get('/django-admin/hi/'+model+'/')
            self.assertNotContains(response,self.draft.title)
            self.assertNotContains(response,'Private discussion')
            form=self.client.get('/django-admin/hi/'+model+'/add/')
            self.assertNotContains(form,self.draft.title)
        self.assertEqual(self.client.get('/dashboard/').context['total_comments'],0)

    def test_upload_manifest_is_never_cached(self):
        item=self.completed_upload()
        response=self.client.get(reverse('upload_part',args=[item.pk]))
        self.assertIn('no-store',response['Cache-Control'])


    def test_removing_uploader_account_does_not_lose_file_ownership_history(self):
        item=self.completed_upload();self.client.post(reverse('upload_finish',args=[item.pk]),{'title':'Owned media'})
        item.refresh_from_db();post=item.post;name=post.image.name;storage=post.image.storage
        self.admin.delete();item.refresh_from_db()
        self.assertIsNone(item.user_id)
        with self.captureOnCommitCallbacks(execute=True):post.delete()
        self.assertFalse(storage.exists(name))
