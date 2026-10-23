import uuid

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
    title = models.CharField(max_length=200, verbose_name="Название контента")
    image = models.ImageField(upload_to='uploads/', verbose_name="Изображение")
    description = models.TextField(blank=True, default='', verbose_name="Описание")
    is_published = models.BooleanField(default=True, verbose_name="Опубликовано")
    author = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='media_items',
        verbose_name="Автор",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата добавления")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "Медиа контент"
        verbose_name_plural = "Медиа контент"
        ordering = ['-created_at']


class Comment(models.Model):
    post = models.ForeignKey(MediaContent, on_delete=models.CASCADE, related_name='comments', verbose_name='Пост')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='post_comments', verbose_name='Автор')
    text = models.TextField(max_length=2000, verbose_name='Комментарий')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата')

    class Meta:
        ordering = ['-created_at', '-pk']
        verbose_name = 'Комментарий'
        verbose_name_plural = 'Комментарии'

    def __str__(self):
        return f'{self.user}: {self.text[:60]}'


class Rating(models.Model):
    post = models.ForeignKey(MediaContent, on_delete=models.CASCADE, related_name='ratings', verbose_name='Пост')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='post_ratings', verbose_name='Пользователь')
    value = models.PositiveSmallIntegerField(choices=[(n, str(n)) for n in range(1, 6)], verbose_name='Оценка')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['post', 'user'], name='one_rating_per_user_post'),
            models.CheckConstraint(condition=models.Q(value__gte=1, value__lte=5), name='rating_between_one_and_five'),
        ]
        verbose_name = 'Оценка'
        verbose_name_plural = 'Оценки'

    def __str__(self):
        return f'{self.user}: {self.value}/5'


# --- Модели для портфолио / резюме ---
class Developer(models.Model):
    name = models.CharField(max_length=100, verbose_name="Имя разработчика")
    role = models.CharField(max_length=100, verbose_name="Роль / Профессия")
    tagline = models.CharField(max_length=200, verbose_name="Слоган")
    photo = models.ImageField(upload_to='developer/', verbose_name="Фотография")
    about_text = models.TextField(verbose_name="О себе")
    experience_years = models.PositiveIntegerField(verbose_name="Опыт работы (лет)")
    email = models.EmailField(verbose_name="Email")
    phone = models.CharField(max_length=20, verbose_name="Телефон")
    address = models.CharField(max_length=200, verbose_name="Адрес")
    github = models.URLField(verbose_name="Ссылка на GitHub", blank=True, null=True)
    linkedin = models.URLField(verbose_name="Ссылка на LinkedIn", blank=True, null=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Разработчик"
        verbose_name_plural = "Разработчики"


class Skill(models.Model):
    name = models.CharField(max_length=50, verbose_name="Название навыка")
    level = models.PositiveIntegerField(verbose_name="Уровень владения (%)")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок сортировки")

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['order']
        verbose_name = "Навык"
        verbose_name_plural = "Навыки"


class Experience(models.Model):
    position = models.CharField(max_length=100, verbose_name="Должность")
    company = models.CharField(max_length=100, verbose_name="Компания")
    period = models.CharField(max_length=50, verbose_name="Период работы")
    description = models.TextField(verbose_name="Обязанности и достижения")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок сортировки")

    def __str__(self):
        return f"{self.position} в {self.company}"

    class Meta:
        ordering = ['order']
        verbose_name = "Опыт работы"
        verbose_name_plural = "Опыт работы"


class Project(models.Model):
    title = models.CharField(max_length=100, verbose_name="Название проекта")
    description = models.TextField(verbose_name="Описание проекта")
    tech_list = models.CharField(max_length=200, verbose_name="Технологии (через запятую)")
    url = models.URLField(verbose_name="Ссылка на проект", blank=True, null=True)
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок сортировки")

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['order']
        verbose_name = "Проект"
        verbose_name_plural = "Проекты"


class Education(models.Model):
    institution = models.CharField(max_length=150, verbose_name="Учебное заведение")
    specialty = models.CharField(max_length=150, verbose_name="Специальность")
    degree = models.CharField(max_length=100, verbose_name="Степень / Квалификация")
    period = models.CharField(max_length=50, verbose_name="Период обучения")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок сортировки")

    def __str__(self):
        return self.institution

    class Meta:
        ordering = ['order']
        verbose_name = "Образование"
        verbose_name_plural = "Образование"


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
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True, verbose_name="Аватар")
    bio = models.TextField(max_length=500, blank=True, verbose_name="О себе")
    city = models.CharField(max_length=100, blank=True, verbose_name="Город")
    birth_date = models.DateField(null=True, blank=True, verbose_name="Дата рождения")

    def __str__(self):
        return f"Профиль: {self.user.username}"

    class Meta:
        verbose_name = "Профиль"
        verbose_name_plural = "Профили"


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
