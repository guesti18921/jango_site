from datetime import timedelta
import uuid

from django import forms
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import permission_required
from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from .csv_tools import csv_response, decode_upload, import_csv, parse_csv
from .models import CSVImportJob, MediaContent


class CSVImportForm(forms.Form):
    file = forms.FileField(label='Файл CSV', widget=forms.ClearableFileInput(attrs={'accept': '.csv,text/csv'}))
    update_existing = forms.BooleanField(
        label='Обновлять существующие записи по ID', required=False, initial=True,
        help_text='Пустой ID создаёт новую запись. Указанный ID обновляет существующую.',
    )

    def clean_file(self):
        self.csv_text = decode_upload(self.cleaned_data['file'])
        return self.cleaned_data['file']


@never_cache
@staff_member_required(login_url='staff-login')
@permission_required('hi.view_mediacontent', raise_exception=True)
@require_GET
def export_media(request):
    return csv_response(MediaContent.objects.all())


@never_cache
@staff_member_required(login_url='staff-login')
@permission_required(('hi.add_mediacontent', 'hi.change_mediacontent'), raise_exception=True)
@require_http_methods(['GET', 'POST'])
def import_media(request):
    if request.method == 'GET' and request.GET.get('template') == '1':
        return csv_response(template=True)
    form = CSVImportForm(request.POST or None, request.FILES or None)
    preview = None
    if request.method == 'POST' and request.POST.get('action') == 'import':
        form = CSVImportForm()
        try:
            with transaction.atomic():
                try:
                    token = uuid.UUID(request.POST.get('job', ''))
                except (ValueError, AttributeError):
                    raise ValidationError('Некорректный запрос импорта. Загрузите CSV заново.')
                # First write locks the batch, including on SQLite. Replays cannot duplicate rows.
                claimed = CSVImportJob.objects.filter(
                    pk=token, user=request.user, consumed=False, expires_at__gt=timezone.now(),
                ).update(consumed=True)
                if not claimed:
                    raise ValidationError('Предпросмотр истёк или уже использован. Загрузите CSV заново.')
                job = CSVImportJob.objects.get(pk=token)
                created, updated = import_csv(job.csv_text, job.update_existing)
                job.csv_text = ''
                job.save(update_fields=['csv_text'])
            messages.success(request, f'CSV импортирован. Добавлено: {created}, обновлено: {updated}.')
            return redirect('dashboard')
        except ValidationError as exc:
            for error in exc.messages:
                messages.error(request, error)
        except DatabaseError:
            messages.error(request, 'Не удалось сохранить данные. Изменения отменены. Повторите импорт.')
    elif request.method == 'POST' and form.is_valid():
        try:
            rows = parse_csv(form.csv_text, form.cleaned_data['update_existing'])
            CSVImportJob.objects.filter(expires_at__lt=timezone.now()).delete()
            job = CSVImportJob.objects.create(
                user=request.user, csv_text=form.csv_text,
                update_existing=form.cleaned_data['update_existing'],
                expires_at=timezone.now() + timedelta(minutes=15),
            )
            preview = {'rows': rows[:20], 'count': len(rows), 'job': job.pk,
                       'created': sum(obj.pk is None for obj in rows),
                       'updated': sum(obj.pk is not None for obj in rows)}
        except ValidationError as exc:
            for error in exc.messages:
                form.add_error(None, error)
    return render(request, 'hi/csv_import.html', {'form': form, 'preview': preview})
