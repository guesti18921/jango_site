from django.utils.translation import gettext_lazy
import uuid
from pathlib import PurePosixPath, PureWindowsPath
from django.core.validators import FileExtensionValidator
from .media_files import EXTENSIONS, MIME_TYPES, extension, media_kind

from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User


class RecoveryState(models.Model):
    """One current challenge and persistent rate limits per account/unknown identity."""
    identity_key = models.CharField(max_length=64, primary_key=True)
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE)
    code_hash = models.CharField(max_length=128, blank=True)
    password_fingerprint = models.CharField(max_length=64, blank=True)
    expires_at = models.DateTimeField(null=True)
    last_sent = models.DateTimeField(null=True)
    window_start = models.DateTimeField(null=True)
    request_count = models.PositiveSmallIntegerField(default=0)
    attempts = models.PositiveSmallIntegerField(default=0)
    consumed = models.BooleanField(default=True)


class CSVImportJob(models.Model):
    """Short-lived, one-use staging area for an administrator's CSV preview."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    csv_text = models.TextField()
    update_existing = models.BooleanField(default=True)
    expires_at = models.DateTimeField()
    consumed = models.BooleanField(default=False)


# --- Модель для медиаконтента ---
class MediaContent(models.Model):
    title = models.CharField(max_length=200, verbose_name=gettext_lazy("Название контента"))
    image = models.FileField(blank=True, upload_to='uploads/', validators=[FileExtensionValidator(allowed_extensions=EXTENSIONS)], verbose_name=gettext_lazy("Медиафайл"), help_text=gettext_lazy("Фото, GIF, видео или аудио. Большие файлы до 30 ГБ загружайте через «Загрузка файлов»."))
    poster = models.ImageField(upload_to='posters/', blank=True, verbose_name=gettext_lazy('Постер'))
    local_path = models.TextField(blank=True, editable=False)
    description = models.TextField(blank=True, default='', verbose_name=gettext_lazy("Описание"))
    is_published = models.BooleanField(default=True, verbose_name=gettext_lazy("Опубликовано"))
    author = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='media_items',
        verbose_name=gettext_lazy("Автор"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=gettext_lazy("Дата добавления"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=gettext_lazy("Дата обновления"))

    @property
    def media_kind(self):
        return media_kind(self.media_name)

    @property
    def media_mime(self):
        return MIME_TYPES.get(extension(self.media_name), '')

    @property
    def media_name(self):
        return PureWindowsPath(self.local_path).name if self.local_path else PurePosixPath(self.image.name).name

    @property
    def media_url(self):
        from django.urls import reverse
        if self.local_path or self.media_kind in ('video', 'audio'):
            return reverse('media_stream', args=[self.pk])
        return self.image.url if self.image else ''

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = gettext_lazy("Медиа контент")
        verbose_name_plural = gettext_lazy("Медиа контент")
        ordering = ['-created_at']


class Comment(models.Model):
    post = models.ForeignKey(MediaContent, on_delete=models.CASCADE, related_name='comments', verbose_name=gettext_lazy('Пост'))
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='post_comments', verbose_name=gettext_lazy('Автор'))
    text = models.TextField(max_length=2000, verbose_name=gettext_lazy('Комментарий'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=gettext_lazy('Дата'))

    class Meta:
        ordering = ['-created_at', '-pk']
        verbose_name = gettext_lazy('Комментарий')
        verbose_name_plural = gettext_lazy('Комментарии')

    def __str__(self):
        return f'{self.user}: {self.text[:60]}'


class Rating(models.Model):
    post = models.ForeignKey(MediaContent, on_delete=models.CASCADE, related_name='ratings', verbose_name=gettext_lazy('Пост'))
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='post_ratings', verbose_name=gettext_lazy('Пользователь'))
    value = models.PositiveSmallIntegerField(choices=[(n, str(n)) for n in range(1, 6)], verbose_name=gettext_lazy('Оценка'))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['post', 'user'], name='one_rating_per_user_post'),
            models.CheckConstraint(condition=models.Q(value__gte=1, value__lte=5), name='rating_between_one_and_five'),
        ]
        verbose_name = gettext_lazy('Оценка')
        verbose_name_plural = gettext_lazy('Оценки')

    def __str__(self):
        return f'{self.user}: {self.value}/5'


# --- Модели для портфолио / резюме ---
class Developer(models.Model):
    name = models.CharField(max_length=100, verbose_name=gettext_lazy("Имя разработчика"))
    role = models.CharField(max_length=100, verbose_name=gettext_lazy("Роль / Профессия"))
    tagline = models.CharField(max_length=200, verbose_name=gettext_lazy("Слоган"))
    photo = models.ImageField(upload_to='developer/', verbose_name=gettext_lazy("Фотография"))
    about_text = models.TextField(verbose_name=gettext_lazy("О себе"))
    experience_years = models.PositiveIntegerField(verbose_name=gettext_lazy("Опыт работы (лет)"))
    email = models.EmailField(verbose_name="Email")
    phone = models.CharField(max_length=20, verbose_name=gettext_lazy("Телефон"))
    address = models.CharField(max_length=200, verbose_name=gettext_lazy("Адрес"))
    github = models.URLField(verbose_name=gettext_lazy("Ссылка на GitHub"), blank=True, null=True)
    linkedin = models.URLField(verbose_name=gettext_lazy("Ссылка на LinkedIn"), blank=True, null=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = gettext_lazy("Разработчик")
        verbose_name_plural = gettext_lazy("Разработчики")


class Skill(models.Model):
    name = models.CharField(max_length=50, verbose_name=gettext_lazy("Название навыка"))
    level = models.PositiveIntegerField(verbose_name=gettext_lazy("Уровень владения (%)"))
    order = models.PositiveIntegerField(default=0, verbose_name=gettext_lazy("Порядок сортировки"))

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['order']
        verbose_name = gettext_lazy("Навык")
        verbose_name_plural = gettext_lazy("Навыки")


class Experience(models.Model):
    position = models.CharField(max_length=100, verbose_name=gettext_lazy("Должность"))
    company = models.CharField(max_length=100, verbose_name=gettext_lazy("Компания"))
    period = models.CharField(max_length=50, verbose_name=gettext_lazy("Период работы"))
    description = models.TextField(verbose_name=gettext_lazy("Обязанности и достижения"))
    order = models.PositiveIntegerField(default=0, verbose_name=gettext_lazy("Порядок сортировки"))

    def __str__(self):
        return (gettext_lazy('%(value0)s в %(value1)s') % {'value0': self.position, 'value1': self.company})

    class Meta:
        ordering = ['order']
        verbose_name = gettext_lazy("Опыт работы")
        verbose_name_plural = gettext_lazy("Опыт работы")


class Project(models.Model):
    title = models.CharField(max_length=100, verbose_name=gettext_lazy("Название проекта"))
    description = models.TextField(verbose_name=gettext_lazy("Описание проекта"))
    tech_list = models.CharField(max_length=200, verbose_name=gettext_lazy("Технологии (через запятую)"))
    url = models.URLField(verbose_name=gettext_lazy("Ссылка на проект"), blank=True, null=True)
    order = models.PositiveIntegerField(default=0, verbose_name=gettext_lazy("Порядок сортировки"))

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['order']
        verbose_name = gettext_lazy("Проект")
        verbose_name_plural = gettext_lazy("Проекты")


class Education(models.Model):
    institution = models.CharField(max_length=150, verbose_name=gettext_lazy("Учебное заведение"))
    specialty = models.CharField(max_length=150, verbose_name=gettext_lazy("Специальность"))
    degree = models.CharField(max_length=100, verbose_name=gettext_lazy("Степень / Квалификация"))
    period = models.CharField(max_length=50, verbose_name=gettext_lazy("Период обучения"))
    order = models.PositiveIntegerField(default=0, verbose_name=gettext_lazy("Порядок сортировки"))

    def __str__(self):
        return self.institution

    class Meta:
        ordering = ['order']
        verbose_name = gettext_lazy("Образование")
        verbose_name_plural = gettext_lazy("Образование")


# --- Модели компании / команды ---
class Company(models.Model):
    name = models.CharField(max_length=100)
    tagline = models.CharField(max_length=200)
    description = models.TextField()
    founded_year = models.PositiveIntegerField()
    team_size = models.PositiveIntegerField()
    mission = models.TextField()
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    address = models.CharField(max_length=200)
    telegram = models.CharField(max_length=50)

    def __str__(self):
        return self.name


class Stat(models.Model):
    label = models.CharField(max_length=100)
    value = models.CharField(max_length=50)
    order = models.PositiveIntegerField(default=0)


class CompanyValue(models.Model):
    title = models.CharField(max_length=100)
    description = models.TextField()
    order = models.PositiveIntegerField(default=0)


class TeamMember(models.Model):
    name = models.CharField(max_length=100)
    role = models.CharField(max_length=100)
    order = models.PositiveIntegerField(default=0)


class HistoryItem(models.Model):
    year = models.CharField(max_length=10)
    event = models.TextField()
    order = models.PositiveIntegerField(default=0)


# --- Профиль пользователя (расширение стандартного User) ---
class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True, verbose_name=gettext_lazy("Аватар"))
    bio = models.TextField(max_length=500, blank=True, verbose_name=gettext_lazy("О себе"))
    city = models.CharField(max_length=100, blank=True, verbose_name=gettext_lazy("Город"))
    birth_date = models.DateField(null=True, blank=True, verbose_name=gettext_lazy("Дата рождения"))

    def __str__(self):
        return (gettext_lazy('Профиль: %(value0)s') % {'value0': self.user.username})

    class Meta:
        verbose_name = gettext_lazy("Профиль")
        verbose_name_plural = gettext_lazy("Профили")


# Автоматически создаём Profile при создании User
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if not hasattr(instance, 'profile'):
        Profile.objects.create(user=instance)
    instance.profile.save()


class MediaUpload(models.Model):
    """Private, resumable upload manifest. Bytes are staged outside MEDIA_ROOT."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    fingerprint = models.CharField(max_length=64)
    size = models.PositiveBigIntegerField()
    offset = models.PositiveBigIntegerField(default=0)
    state = models.CharField(max_length=12, default='uploading')
    post = models.ForeignKey(MediaContent, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        indexes = [models.Index(fields=['user', 'fingerprint', 'state'], name='media_upload_resume_idx')]
