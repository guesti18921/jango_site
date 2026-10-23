from django.utils.translation import gettext_lazy
from django.contrib import admin
from .forms import MediaContentAdminForm
from .models import (
    Developer, Skill, Experience, Project, Education,
    Company, Stat, CompanyValue, TeamMember, HistoryItem,
    MediaContent, Profile, Comment, Rating,
)


# ============================================
# Медиа-контент (для API мобильного приложения)
# ============================================
@admin.register(MediaContent)
class MediaContentAdmin(admin.ModelAdmin):
    form = MediaContentAdminForm
    change_list_template = 'admin/hi/mediacontent/change_list.html'
    list_display = ('title', 'author', 'is_published', 'created_at', 'updated_at')
    list_editable = ('is_published',)
    list_filter = ('is_published', 'created_at', 'author')
    search_fields = ('title', 'description')
    readonly_fields = ('created_at', 'updated_at', 'author')
    fieldsets = (
        (gettext_lazy('Контент'), {
            'fields': ('title', 'description', 'image')
        }),
        (gettext_lazy('Публикация'), {
            'fields': ('is_published',)
        }),
        (gettext_lazy('Служебное'), {
            'fields': ('author', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    def save_model(self, request, obj, form, change):
        # Автоматически ставим автора — текущего залогиненного админа
        if not obj.author:
            obj.author = request.user
        super().save_model(request, obj, form, change)


# ============================================
# Профиль разработчика
# ============================================
@admin.register(Developer)
class DeveloperAdmin(admin.ModelAdmin):
    list_display = ('name', 'role', 'experience_years')
    fieldsets = (
        (gettext_lazy('Основное'), {'fields': ('name', 'role', 'tagline', 'photo', 'about_text', 'experience_years')}),
        (gettext_lazy('Контакты'), {'fields': ('email', 'phone', 'address', 'github', 'linkedin')}),
    )

    def has_add_permission(self, request):
        # Ограничение: можно создать только одного разработчика в базе
        return not Developer.objects.exists()


# ============================================
# Навыки / Опыт / Проекты / Образование
# ============================================
@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ('name', 'level', 'order')
    list_editable = ('level', 'order')
    list_display_links = ('name',)


@admin.register(Experience)
class ExperienceAdmin(admin.ModelAdmin):
    list_display = ('position', 'company', 'period', 'order')
    list_editable = ('order',)
    list_display_links = ('position',)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'url', 'order')
    list_editable = ('order',)
    list_display_links = ('title',)


@admin.register(Education)
class EducationAdmin(admin.ModelAdmin):
    list_display = ('institution', 'specialty', 'degree', 'period', 'order')
    list_editable = ('order',)
    list_display_links = ('institution',)


# ============================================
# Компания / Команда / История
# ============================================
@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'founded_year', 'team_size')
    fieldsets = (
        (gettext_lazy('Основное'), {'fields': ('name', 'tagline', 'description', 'founded_year', 'team_size', 'mission')}),
        (gettext_lazy('Контакты'), {'fields': ('email', 'phone', 'address', 'telegram')}),
    )

    def has_add_permission(self, request):
        return not Company.objects.exists()


@admin.register(Stat)
class StatAdmin(admin.ModelAdmin):
    list_display = ('label', 'value', 'order')
    list_editable = ('value', 'order')
    list_display_links = ('label',)


@admin.register(CompanyValue)
class CompanyValueAdmin(admin.ModelAdmin):
    list_display = ('title', 'order')
    list_editable = ('order',)
    list_display_links = ('title',)


@admin.register(TeamMember)
class TeamMemberAdmin(admin.ModelAdmin):
    list_display = ('name', 'role', 'order')
    list_editable = ('order',)
    list_display_links = ('name',)


@admin.register(HistoryItem)
class HistoryItemAdmin(admin.ModelAdmin):
    list_display = ('year', 'event', 'order')
    list_editable = ('order',)
    list_display_links = ('year',)


# ============================================
# Профиль пользователя
# ============================================
@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'city', 'birth_date')
    search_fields = ('user__username', 'city')

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('user', 'post', 'text', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('text', 'user__username', 'post__title')
    list_select_related = ('user', 'post')
    readonly_fields = ('created_at',)


@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ('user', 'post', 'value', 'updated_at')
    list_filter = ('value',)
    search_fields = ('user__username', 'post__title')
    list_select_related = ('user', 'post')
    readonly_fields = ('updated_at',)


# Use the editorial workspace as the admin home; native model URLs stay available.
from .dashboard_views import dashboard
admin.site.index = dashboard
