"""Messages used by the same-origin JavaScript translation catalog."""
from django.utils.translation import gettext_noop

CLIENT_MESSAGES = (
    gettext_noop('Комментарии и оценки'), gettext_noop('Комментарии'),
    gettext_noop('Пока нет медиа.'), gettext_noop('Всего записей:'),
    gettext_noop('Показано:'), gettext_noop('Не удалось загрузить. Проверьте соединение.'),
)
