from django.shortcuts import render
from django.utils.translation import gettext as _


def error_page(request, code):
    messages = {
        400: (_('Не удалось открыть страницу'), _('Проверьте адрес и повторите запрос.')),
        403: (_('Нет доступа'), _('Войдите в нужный аккаунт или вернитесь в коллекцию.')),
        413: (_('Файл слишком большой'), _('Для файлов до 30 ГБ используйте раздел «Загрузка файлов». Аватар и постер — до 10 МБ.')),
        404: (_('Здесь пока ничего нет'), _('Страница или файл недоступны. Возможно, публикацию переместили или скрыли.')),
        500: (_('Не удалось загрузить страницу'), _('Попробуйте обновить страницу чуть позже.')),
    }
    title, description = messages[code]
    response = render(request, 'hi/error.html', {'code': code, 'title': title, 'description': description}, status=code)
    response['Cache-Control'] = 'no-store'
    return response


def bad_request(request, exception):
    return error_page(request, 400)


def permission_denied(request, exception):
    return error_page(request, 403)


def not_found(request, exception):
    return error_page(request, 404)


def server_error(request):
    return error_page(request, 500)


def csrf_failure(request, reason=''):
    return error_page(request, 403)
