"""Register a movie already on the server, without copying its bytes."""
from pathlib import Path
from django.conf import settings
from django.contrib.admin.models import ADDITION, LogEntry
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from hi.media_files import extension, VIDEO_EXTENSIONS, validate_upload
from hi.models import MediaContent


class Command(BaseCommand):
    help = 'Connect an existing server movie without copying it. Keep the source file in place.'

    def add_arguments(self, parser):
        parser.add_argument('path')
        parser.add_argument('--author', required=True, help='Staff account with add-media permission')
        parser.add_argument('--title')
        parser.add_argument('--description', default='')
        parser.add_argument('--poster')
        parser.add_argument('--draft', action='store_true')

    def handle(self, *args, **options):
        source = Path(options['path']).expanduser().resolve()
        if not source.is_file(): raise CommandError('Movie file does not exist.')
        if extension(source.name) not in VIDEO_EXTENSIONS: raise CommandError('Choose a supported video file.')
        author = User.objects.filter(username=options['author'], is_active=True, is_staff=True).first()
        if not author or not author.has_perm('hi.add_mediacontent'): raise CommandError('Author needs staff status and permission to add media.')
        if MediaContent.objects.filter(local_path=str(source)).exists(): raise CommandError('This file is already connected.')
        poster_path = Path(options['poster']).expanduser().resolve() if options.get('poster') else None
        try:
            with source.open('rb') as file: validate_upload(File(file, name=source.name))
            if poster_path:
                if not poster_path.is_file() or poster_path.stat().st_size > 10 * 1024 ** 2: raise CommandError('Poster must exist and be at most 10 MB.')
                from PIL import Image
                with Image.open(poster_path) as image: image.verify()
            title = options['title'] or source.stem
            if not title.strip() or len(title)>200: raise CommandError('Title must contain 1 to 200 characters.')
            post = None
            try:
                with transaction.atomic():
                    post = MediaContent(title=title, description=options['description'], local_path=str(source), author=author, is_published=not options['draft'])
                    if poster_path:
                        with poster_path.open('rb') as file: post.poster.save(poster_path.name, File(file), save=False)
                    post.save()
                    LogEntry.objects.create(user=author, content_type=ContentType.objects.get_for_model(post), object_id=str(post.pk), object_repr=post.title, action_flag=ADDITION, change_message='Connected existing server movie')
            except Exception:
                if post and post.poster: post.poster.delete(save=False)
                raise
        except (OSError, ValueError, ValidationError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f'Connected post #{post.pk}: /posts/{post.pk}/ (no movie copy created)'))
