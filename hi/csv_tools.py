from django.utils.translation import gettext_lazy
"""CSV interchange for media metadata; image bytes stay in MEDIA_ROOT."""
import csv
import io
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone

from .models import MediaContent

COLUMNS = ('id', 'title', 'description', 'image', 'author', 'is_published')
MAX_BYTES = 1024 * 1024
MAX_ROWS = 1000


def dangerous_cell(value):
    return value.lstrip(' \t\r\n').startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n'))


def escape_cell(value):
    # Quote spreadsheet formulas as text, and escape literal leading apostrophes.
    value = str(value)
    return "'" + value if value.startswith("'") or dangerous_cell(value) else value


def unescape_cell(value):
    if value.startswith("'") and (value[1:].startswith("'") or dangerous_cell(value[1:])):
        return value[1:]
    return value


def csv_response(queryset=None, template=False):
    filename = 'media-template.csv' if template else f'media-{timezone.localdate():%Y-%m-%d}.csv'
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Cache-Control'] = 'no-store'
    response.write('\ufeff')  # Excel recognizes Cyrillic as UTF-8.
    writer = csv.writer(response, delimiter=';')
    writer.writerow(COLUMNS)
    if not template:
        for item in queryset.select_related('author').order_by('pk').iterator():
            writer.writerow([item.pk, escape_cell(item.title), escape_cell(item.description),
                             (f'local:{item.pk}' if item.local_path else item.image.name), escape_cell(item.author.username if item.author else ''),
                             '1' if item.is_published else '0'])
    return response


def decode_upload(upload):
    if not upload.name.lower().endswith('.csv'):
        raise ValidationError(gettext_lazy('Выберите файл с расширением .csv.'))
    raw = upload.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValidationError(gettext_lazy('Размер CSV не должен превышать 1 МБ.'))
    if not raw or b'\x00' in raw:
        raise ValidationError(gettext_lazy('Файл пуст или не является текстовым CSV.'))
    try:
        return raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            return raw.decode('cp1251')
        except UnicodeDecodeError as exc:
            raise ValidationError(gettext_lazy('Сохраните CSV в кодировке UTF-8 или Windows-1251.')) from exc


def validate_image_path(value):
    path = PurePosixPath(value)
    if (not value.startswith('uploads/') or '\\' in value or ':' in value
            or '..' in path.parts or str(path) != value):
        raise ValidationError(gettext_lazy('image: нужен относительный путь uploads/имя_файла без ../ и URL.'))
    try:
        absolute = Path(default_storage.path(value)).resolve()
        absolute.relative_to((Path(settings.MEDIA_ROOT) / 'uploads').resolve())
        exists = absolute.is_file() and default_storage.exists(value)
    except (ValueError, OSError, NotImplementedError):
        exists = False
    if not exists:
        raise ValidationError((gettext_lazy('image: файл «%(value0)s» не найден в папке media/uploads.') % {'value0': value}))
    return value


def parse_csv(text, update_existing=True, lock=False):
    """Validate every row before returning model instances. Does not write data."""
    try:
        first_line = text.splitlines()[0] if text.splitlines() else ''
        delimiter = max((';', ',', '\t'), key=first_line.count)
        reader = csv.reader(io.StringIO(text, newline=''), delimiter=delimiter, strict=True)
        header = next(reader, [])
        if len(header) != len(COLUMNS) or set(header) != set(COLUMNS):
            raise ValidationError(gettext_lazy('Неверные заголовки. Используйте колонки: ') + ';'.join(COLUMNS))
        rows, errors, seen = [], [], set()
        for values in reader:
            if not values or all(not cell.strip() for cell in values):
                continue
            if len(rows) + len(errors) >= MAX_ROWS:
                raise ValidationError((gettext_lazy('В одном CSV допускается не более %(value0)s записей.') % {'value0': MAX_ROWS}))
            line = reader.line_num
            try:
                if len(values) != len(header):
                    raise ValidationError(gettext_lazy('число значений не совпадает с числом колонок.'))
                row = dict(zip(header, values))
                identifier = row['id'].strip()
                if identifier:
                    if not identifier.isascii() or not identifier.isdecimal() or not 0 < int(identifier) <= 9223372036854775807:
                        raise ValidationError(gettext_lazy('id: требуется положительное целое число.'))
                    identifier = int(identifier)
                    if identifier in seen:
                        raise ValidationError((gettext_lazy('id %(value0)s повторяется в файле.') % {'value0': identifier}))
                    seen.add(identifier)
                    if not update_existing:
                        raise ValidationError(gettext_lazy('для обновления ID включите соответствующий флажок или очистите колонку id для новой записи.'))
                    query = MediaContent.objects.select_for_update() if lock else MediaContent.objects
                    obj = query.filter(pk=identifier).first()
                    if obj is None:
                        raise ValidationError((gettext_lazy('запись с id %(value0)s не найдена. Для создания оставьте id пустым.') % {'value0': identifier}))
                else:
                    obj = MediaContent()
                title = unescape_cell(row['title'])
                if not title.strip():
                    raise ValidationError(gettext_lazy('title: название не может быть пустым.'))
                author_name = unescape_cell(row['author']).strip()
                author = User.objects.filter(username=author_name).first() if author_name else None
                if author_name and author is None:
                    raise ValidationError((gettext_lazy('author: пользователь «%(value0)s» не найден.') % {'value0': author_name}))
                status = row['is_published'].strip().lower()
                if status not in ('1', '0', 'true', 'false'):
                    raise ValidationError(gettext_lazy('is_published: допустимы 1, 0, true или false.'))
                obj.title = title
                obj.description = unescape_cell(row['description'])
                media_path = row['image'].strip()
                if not (obj.pk and obj.local_path and media_path == f'local:{obj.pk}'):
                    obj.image = validate_image_path(media_path)
                    obj.local_path = ''
                obj.author = author
                obj.is_published = status in ('1', 'true')
                obj.full_clean(exclude=['created_at', 'updated_at'])
                rows.append(obj)
            except ValidationError as exc:
                errors.append((gettext_lazy('Строка %(value0)s: ') % {'value0': line}) + ' '.join(exc.messages))
                if len(errors) >= 20:
                    break
        if errors:
            raise ValidationError(errors)
        if not rows:
            raise ValidationError(gettext_lazy('В CSV нет записей. Добавьте строки после заголовков.'))
        return rows
    except csv.Error as exc:
        raise ValidationError((gettext_lazy('Некорректный CSV: %(value0)s. Проверьте кавычки и разделители.') % {'value0': exc})) from exc


@transaction.atomic
def import_csv(text, update_existing=True):
    rows = parse_csv(text, update_existing, lock=True)
    created = sum(obj.pk is None for obj in rows)
    for obj in rows:
        obj.save()
    return created, len(rows) - created
