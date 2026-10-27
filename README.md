# VEYRA — локальный Django-проект

Медиаколлекция, личный профиль, панель администратора и API для мобильного приложения.
Общее оформление адаптируется к телефону; внешние шрифты и CDN не требуются.

## Обновление существующего проекта

Остановите сервер (Ctrl+C), откройте терминал в папке с `manage.py` и выполните:

```console
git pull origin main
python manage.py migrate
python manage.py runserver
```

Используйте своё активное виртуальное окружение. Миграции добавляют таблицы
восстановления, импорта, комментариев и оценок: существующие пользователи,
пароли и медиаконтент сохраняются. Само обновление дизайна новых миграций не требует.
Скопируйте `db.sqlite3` перед обновлением, если нужна дополнительная локальная резервная копия.

Для нового окружения понадобятся Django (5.2 или новее), Django REST Framework и Pillow:

```console
python -m pip install Django djangorestframework Pillow
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Восстановление доступа без почты

1. На странице входа нажмите **Восстановить доступ** (`/recover/`).
2. Введите свой логин или email, сохранённый в аккаунте.
3. В терминале сервера найдите блок `[ACCOUNT RECOVERY]`:

   ```text
   [ACCOUNT RECOVERY]
   User: 'your_username'
   Code: 123456
   Request: a1b2c3d4
   Valid for 10 minutes. Enter only on the local recovery page.
   ```

   Код выше — только пример. Нужен код, который выведет ваш сервер.
   `Request` совпадает с номером запроса на странице и помогает найти нужный блок.
4. В том же браузере введите код и дважды новый пароль. Затем войдите заново.

Код выводится **на компьютере, где запущен сервер**, а не в консоли браузера.
Если сайтом пользуется другой человек, администратор проверяет, кому принадлежит
аккаунт, и передаёт код его владельцу. Письма и ссылки восстановления не используются.
Локальный IP не нужен в коде и не влияет на подтверждение.

### Ограничения

- Код действует 10 минут, доступно 5 попыток отправки формы.
- Повторный запрос — через 60 секунд, не более 5 запросов за час на аккаунт.
  Логин и email одного аккаунта используют общее ограничение, включая другие браузеры.
- Новый код отменяет предыдущий. Для подтверждения нужна исходная сессия браузера.
- Успешное восстановление или смена пароля другим способом делает код недействительным.
  После смены пароля прежние сеансы входа также перестают действовать.
- В базе хранится хеш кода, в сессии — только случайный идентификатор запроса.
- Для неизвестного, неактивного аккаунта или аккаунта без пароля код не печатается.
  Страница показывает одинаковое сообщение, чтобы не раскрывать наличие аккаунта.
- Если один email указан у нескольких пользователей, используйте точный логин.
- Старая страница `/password-reset/` и её шаблоны удалены.

Этот способ рассчитан на локальный сервер с доступом владельца к терминалу.

## Проверка

```console
python manage.py test hi
python manage.py check
python manage.py makemigrations --check --dry-run
```

Автотесты проверяют восстановление, ограничения, истечение срока, повторное
использование кода, валидацию паролей, CSRF, CSV, комментарии, оценки,
переключение языка и существующие страницы сайта.

## Тёмный интерфейс и два языка

Основные страницы, вход и восстановление, профиль, панель управления, CSV,
приложение и Django-админка используют тёмную тему с лаймовым акцентом.
На компьютере навигация находится слева, на телефоне — внизу экрана.

Переключатель **RU / EN** находится в верхней части интерфейса. Он переводит
навигацию, формы, подсказки и сообщения, сохраняя выбор в браузере на год.
Названия постов, описания, комментарии и имена пользователей остаются такими,
какими их написал автор. База данных общая для обоих языков.

Есть плавное появление карточек, реакции кнопок и переключателя языка, а в
поддерживающих браузерах — переход изображения из ленты в пост. Настройка системы
«Уменьшение движения» отключает декоративные анимации. Основные формы и смена языка
работают без JavaScript. Шрифты и скрипты не требуют подключения к интернету.

Готовые файлы переводов `.mo` включены в репозиторий: устанавливать GNU gettext
на Windows для обычного запуска не нужно. После изменения исходных переводов
`.po` разработчику нужно заново выполнить `python manage.py compilemessages`.
После обновления перезагрузите открытую страницу сочетанием **Ctrl+F5**.

Ключ Django больше не хранится в коде: при первом запуске создаётся локальный
файл `.django-secret-key`, исключённый из Git. Сохраните его между перезапусками;
для своего окружения можно задать `DJANGO_SECRET_KEY`. После первого обновления
нужно войти в аккаунт заново. Пароли пользователей не меняются.

## Экспорт и импорт CSV

В панели управления (`/dashboard/`) и списке медиаконтента Django-админки доступны
**Экспорт CSV** и **Импорт CSV**. Нужны аккаунт персонала и права на медиаконтент:
просмотр — для экспорта; добавление и изменение — для импорта. У суперпользователя
эти права есть автоматически.

Экспорт скачивает все медиаматериалы, включая неопубликованные. Формат — UTF-8 с BOM,
разделитель `;`, совместимый с кириллицей в Excel. Колонки:

| Колонка | Значение |
| --- | --- |
| id | Существующий ID для обновления; пустое значение для новой записи |
| title | Обязательное название, до 200 символов |
| description | Описание; может содержать переносы строк, кавычки и разделители |
| image | Относительный путь к существующему изображению: `uploads/photo.jpg` |
| author | Точный логин существующего пользователя или пустое значение |
| is_published | `1` / `0` или `true` / `false` |

Для импорта скачайте шаблон на странице импорта или отредактируйте экспорт. Файл
может содержать до 1000 записей и занимать до 1 МБ. Поддерживаются UTF-8 и Windows-1251,
разделители `;`, `,` и табуляция. Заголовки обязательны; их порядок можно менять.

Нажмите **Проверить файл**: проверяются все строки, показывается до 20 записей и
общее число добавлений/обновлений. После проверки нажмите **Подтвердить импорт**.
Предпросмотр действует 15 минут, принадлежит текущему администратору и применяется
один раз. Проверка повторяется при подтверждении. Ошибка в любой строке или при
сохранении отменяет весь импорт. Сообщения указывают номер строки CSV.

Пустой ID каждый раз создаёт новый материал. Указанный ID должен уже существовать;
при выключенном флажке обновления строки с ID не принимаются. Повторный импорт
исходного файла с пустыми ID создаст новые записи: для последующего редактирования
сначала получите свежий экспорт с назначенными ID.

Импорт не удаляет материалы. Изображения не включаются в CSV и не скачиваются по
URL: скопируйте нужные файлы в `media/uploads` заранее. Время создания существующих
записей сохраняется; время обновления назначается автоматически. Новые записи
получают текущие даты. Ячейки, похожие на формулы, экранируются при экспорте и
восстанавливаются при обратном импорте.

## Комментарии и оценки постов

Нажмите на изображение или название материала в медиаколлекции. На странице поста
можно оставить комментарий (до 2000 символов) и оценку от 1 до 5. Один аккаунт имеет
одну оценку на пост; повторная отправка меняет её. Средняя оценка, число голосов и
число комментариев видны в коллекции. В приложении `/app/` есть переход
**Комментарии и оценки** из открытого материала.

Комментарии отображаются по 20 на страницу, начиная с новых. Автор может удалить
свой комментарий. Сотрудник с правом `hi.delete_comment` может удалять чужие;
суперпользователь имеет это право автоматически. Комментарии и оценки также
доступны в Django-админке. Вход обязателен для обсуждения и голосования.
Неопубликованные материалы доступны на сайте только персоналу.

## Общая Wi-Fi-сеть / локальная сеть

Проект запускается **на одном компьютере**. На остальных компьютерах достаточно
браузера; данные, изображения, комментарии и оценки будут общими и хранятся на
компьютере с сервером.

На компьютере с проектом остановите сервер (Ctrl+C), затем:

```console
git pull origin main
python manage.py migrate
python manage.py runlan
```

Команда определяет частные IPv4-адреса компьютера, добавляет конкретные адреса в
`ALLOWED_HOSTS` и запускает сервер на порту 8000. Она печатает, например:

```text
Open on another computer connected to the same Wi-Fi:
  http://192.168.1.10:8000/
```

На другом компьютере в той же Wi-Fi-сети откройте **ссылку из своего терминала**.
Адрес выше — пример. `127.0.0.1` на другом компьютере указывает на него самого.
Каждый человек может зарегистрировать свой аккаунт. Терминал сервера оставляйте
открытым; выключение этого компьютера или остановка команды отключает сайт.
Коды восстановления аккаунтов по-прежнему выводятся только на компьютере сервера.

### Если адрес не определился или показано несколько

В Windows выполните `ipconfig` и найдите IPv4-адрес адаптера **Беспроводная сеть /
Wi-Fi**, подключённого к нужному роутеру. Укажите его явно:

```console
python manage.py runlan --ip 192.168.1.10
```

Другой порт можно задать через `--port 8080`. Если роутер сменил IP компьютера,
перезапустите `runlan` и используйте новую ссылку.

### Если второй компьютер не открывает сайт

- Сначала проверьте ссылку с IP в браузере компьютера, где запущен сервер.
- В запросе брандмауэра Windows разрешите Python доступ к **частным сетям**.
  Домашняя доверенная Wi-Fi-сеть в настройках Windows должна иметь профиль «Частная».
- При необходимости в PowerShell **от имени администратора** разрешите порт только
  для частной локальной сети (для другого порта замените 8000):

  ```powershell
  New-NetFirewallRule -DisplayName "Django LAN 8000" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -RemoteAddress LocalSubnet -Profile Private
  ```

  Удалить это правило можно командой:

  ```powershell
  Remove-NetFirewallRule -DisplayName "Django LAN 8000"
  ```

- Устройства должны находиться в одной обычной сети, а не в изолированной гостевой.
  Если на роутере включена изоляция Wi-Fi-клиентов (AP/client isolation), она может
  блокировать соединение между компьютерами. VPN также может менять маршрутизацию.

Для ручного запуска обычного `runserver` список адресов можно задать переменной
окружения `DJANGO_ALLOWED_HOSTS` (через запятую). Команда `runlan` делает это в
настройках текущего процесса автоматически. Проброс портов на роутере для этой
локальной схемы не требуется.

## Современная панель управления

`/dashboard/` открывает рабочий стол коллекции:
реальные счётчики публикаций, комментариев и пользователей, последние комментарии,
быстрые переходы к CSV и остальным моделям. Никаких демонстрационных записей в базу
не добавляется.

В разделе «Публикации» есть поиск по названию, описанию и логину автора, фильтр
опубликованных материалов и черновиков, переключение списка/карточек, постраничный
вывод по 12 записей. Массовое действие применяется только к отмеченным записям:
их можно опубликовать или перевести в черновики. Флажок в заголовке выбирает только
текущую страницу. Поиск и фильтры сохраняются при переходе между страницами.

Комментарии можно искать, открывать в обсуждении, редактировать и удалять.
В списке пользователей доступны поиск и переход к карточке аккаунта. Добавление,
редактирование, удаление материалов и управление аккаунтами используют формы Django
с прежней проверкой данных. Остальные модели доступны через «Все разделы», группы —
в блоке «Модерация и доступ» на странице разделов.

Нужен статус персонала и права соответствующей модели: просмотр или изменение —
для списков, изменение медиаконтента — для массовой публикации, удаление комментария
— для модерации. У суперпользователя все права есть автоматически. Изменения статуса
и удаления из нового рабочего стола записываются в журнал Django-админки. Формы
защищены CSRF. Рабочий стол и редакторы поддерживают RU / EN и узкие экраны.


### Media posts and avatars

Posts accept photos and animated GIF/WebP, video (MP4, WebM, MOV, MKV, AVI, OGV, MPEG, 3GP) and audio (MP3, WAV, OGG/Opus, M4A, AAC, FLAC, WMA, AIFF), up to 30 GB per file through the resumable uploader. Actual playback depends on browser/codec support; video and audio include a download link. HEIC/HEIF and TIFF are available as downloads rather than broken inline images. Native Apple Live Photo pairs are not merged; upload the exported video or GIF to show motion. Files are preserved without transcoding.

The existing `image` database column and CSV/API field remain for compatibility and now refer to any supported media file. The API adds `media_kind`, `media_mime`, and `media_name`. Run `python manage.py migrate` after updating. Profile GIF avatars remain animated, and the current avatar is displayed in discussions and the management workspace.


### Movies up to 30 GB: upload, resume, and local files

Open **Управление → Загрузка файлов**. Choose a file, title, description, and optionally a poster up to 10 MB. Use **Загрузить и сохранить**. The page displays percentage, transferred bytes, average speed, and estimated remaining time. Movies can also be saved as drafts by clearing **Опубликовано**.

Transfers use 8 MiB requests. Pause stops the current request; Resume asks the server for its acknowledged offset, so an interrupted chunk can be resent safely. After closing the page or restarting the server/browser, select the same original file again. The file's name, size, last-modified time, and first/last 64 KiB identify the transfer. Do not modify the source file during a transfer. After a page reload, re-enter publication metadata and reselect the poster. A successful retry of finalization returns the existing post instead of duplicating it. Switching browsers is supported for the same signed-in account, because the server also looks up active manifests.

The server checks disk space before starting, reserves space for other active transfers, and keeps a 256 MiB safety margin. Partial bytes live in `.media-uploads/`, outside the public media folder. Keep the SQLite database and that folder when restarting or moving the server. Staging and `MEDIA_ROOT` must be on the same disk: finalization renames the file instead of creating another full movie copy. The ordinary Django file form remains intended for files up to 100 MB; use the new page for movies.

Resume is available for 7 days after the most recent confirmed chunk. Cancel removes the temporary file immediately. Expired partials are reclaimed when a new transfer starts (up to 20 per start); to reclaim them all manually, run:

```console
python manage.py cleanupuploads
```

To connect a movie **already on the server computer** without copying or uploading it:

```console
python manage.py addfilm "D:\Films\movie.mp4" --author YOUR_ADMIN_LOGIN --title "Movie title" --poster "D:\Films\poster.jpg"
```

`--poster` is optional. `--draft` keeps the movie unpublished. The author must be an active staff account with permission to add media. The command validates the source and records an admin history entry. The movie remains at its original path; moving, deleting, or disconnecting its disk makes it unavailable. The original movie is never deleted by the upload cleanup command. Absolute server paths are not exposed by the API or CSV. Existing-file posts use `local:<post id>` in the CSV `image` column; this token can update the same existing post but cannot attach an arbitrary server path to a new post. Posters remain outside CSV.

Movies use `/files/<post id>/` with HTTP byte ranges (206), suffix ranges, HEAD, and 416 for invalid ranges. This allows seeking without reading the whole movie into memory. Draft files are available only to signed-in staff; published media retains the existing public API behavior. Video playback still depends on the browser/codec: MP4/H.264/AAC is recommended, and unsupported formats can be downloaded. There is no automatic transcoding.

Settings: `MAX_MEDIA_UPLOAD_BYTES` (30 GiB), `MEDIA_CHUNK_BYTES` (8 MiB), `MEDIA_UPLOAD_RESERVE_BYTES` (256 MiB), `MEDIA_UPLOAD_ROOT`, and `MEDIA_UPLOAD_TTL_DAYS` (7). Reverse proxies must allow at least the chunk size plus small metadata/poster requests. This local prototype uses Django's development server; production hosting needs a properly configured web server. Tests exercise the 30 GiB declaration and >32-bit seeking using sparse files, rather than transferring an actual 30 GiB movie.


### Gallery audit and maintenance improvements

See [AUDIT.md](AUDIT.md) for findings, fixes, validation, and operating boundaries. The gallery is now bounded to 18 publications per page, defers offscreen video traffic and decodes a still frame for nearby videos without posters, uses indexed engagement summaries, and consistently protects drafts in both media routes and native moderation tools. Logout uses a CSRF-protected POST. Oversized form bodies are rejected before parsing; movies still use bounded chunk uploads. Managed resumable-upload files are freed after committed deletion/replacement only when no post references them; connected external originals are never deleted. Existing loose files remain available for later CSV attachment and are not automatically pruned.

When hosting behind a proxy, route `/media/` requests through Django's permission-checking handler rather than serving upload/poster directories publicly. Local HTTP operation is retained; production HTTPS configuration is outside this local audit. Run migrations and refresh with Ctrl+F5 after updating.


### Automatic video previews

Videos without an uploaded poster show a paused frame from 12% into the clip (capped at 3 seconds) in the feed, post detail, and application cards. Preview loading starts only near the viewport. It never calls `play()` and does not change the volume or mute setting of the actual player. An uploaded poster takes precedence and avoids fetching video data for its preview. Audio players retain their existing loading behavior.

This uses the browser video decoder and the existing permission-checked range endpoint; no FFmpeg installation, background task, migration, or re-upload is required. Browser codec support still applies. For unsupported video formats or a deliberately selected cover image, upload a poster as before. Refresh the page with Ctrl+F5 after pulling the update.


### Silent hover playback

With a mouse, hovering a video in the feed or an application card for 180 ms starts a muted preview lasting at most four seconds. Moving away pauses it and restores the previous position, mute setting, and loop setting. Feed previews temporarily hide native controls; clicking the picture switches to normal playback with those controls and the previous sound settings. Manually started playback continues when the pointer leaves. Detail pages retain normal explicit playback.

Hover playback yields to any already playing music or manually started movie. Starting another player stops the hover preview. Application navigation, element removal, and a hidden browser tab also release previews. Touch devices retain normal tap playback. Explicit posters support hover playback too; the application uses the same video-card presentation whether or not a poster exists.


### Media presentation and loading polish

- Feed media stages share a 4:3 shape and aligned grid rows. Portrait photos are cropped only in cards; opening a post shows the whole image. Application cards use the same proportions. Titles wrap safely and are limited to two lines in cards.
- An automatic video cover starts at 12% of the duration, capped at 3 seconds. If a tiny local pixel sample is almost black, one more frame is tried at 30%, capped at 6 seconds. This is a bounded heuristic, not scene recognition; a manual poster always takes precedence. Data-saver connections use only the initial sample.
- Images and videos have fixed-size loading stages with a restrained fade. Broken images show a readable fallback, including dynamically inserted application images. Reduced-motion preferences suppress loading animations and hover playback.
- Hover previews stop after four seconds and restore the earlier frame and player settings. Manual playback retains its controls and priority. Touch devices use explicit playback.
- Initial video-frame work is queued with at most two active decoders, reduced to one with data saver or a 2G connection. Offscreen videos and audio retain deferred loading. Data saver/2G suppress automatic hover playback. Browser buffering remains controlled by the browser; this does not transcode or recompress the original files.
- Mobile layouts keep long headings and metadata within the screen, maintain fixed media geometry, and retain larger download/navigation targets. No database migration or additional dependency is required.

### VEYRA visual identity

The site uses the VEYRA name in both languages, a folded V mark, and a shared wordmark in the site navigation, management navigation, guest pages, native Django admin, error pages, and footer. Browser titles, anonymous-author fallbacks, local sender display name, and the installed application use the same identity. The login illustration uses the same mark.

Editable SVG sources and exported favicon/application icons are in `hi/static/hi/brand/`. `hi/templates/hi/brand.html` is the shared navigation lockup; `brand_meta.html` supplies browser and home-screen metadata. `hi/static/hi/brand.css` controls its spacing and responsive sizes. Icons are prebuilt; no image-processing runtime dependency is required. Pull the update, restart Django, and refresh with Ctrl+F5. An already installed app may need to be reopened or reinstalled if the operating system keeps its old name/icon cached.


### Focused administration start page

`/django-admin/` now opens a gallery-focused start page. Publications, comments, and users appear first in a fixed order in RU and EN. Ratings, profiles, and permission groups appear under Moderation and access. Portfolio/company/team models remain registered at their original URLs and are grouped in a closed Additional sections disclosure. `/django-admin/hi/` uses the same focused layout. Every group is built from Django's permission-filtered app list.

The prominent Add photos or video action opens the existing resumable upload page (including support for audio and large files). The dashboard uses the same main action and retains a secondary link to the original publication form. MediaContent is displayed as Publication/Publications without changing its model identity, table, API or permission codenames. Company/Developer add checks now enforce both model permission and their existing single-record limit.

Migration 0014 records presentation metadata only. Pull, run migrations, restart Django and refresh with Ctrl+F5. No content is removed by grouping the navigation.


## VEYRA visual redesign — 2026-10-24

The collection, management dashboard and native Django admin now use a neutral
charcoal palette (#101113 / #17191C), ivory primary actions and a restrained
champagne accent (#C8B89A). Legacy green literal colors were normalized across
authentication, upload and app surfaces. Existing vector branding and all raster
icons use the same palette; version 26 assets invalidate old browser/PWA styling.

Collection cards have no surrounding filled frame, use 6px media corners and
compact 15px titles. The grid uses three columns on large screens, two on medium
screens and one on phones. Stable preview aspect ratios and DOM reading order
are retained. Video/audio download links remain on detail pages; compact video
players expose their download recovery link when playback fails. No playback,
sound, upload, permission or database logic was changed.

Management statistics and tables have quieter surfaces and larger readable
labels; statistics stack on phones. Native admin lists use horizontal dividers,
60px rows, ivory action buttons and a 224px navigation panel. Form validation,
filters, bulk actions and permission-aware links remain native Django behavior.

Validation: Django system checks and migration drift check passed; all 120 tests
passed. Chromium route checks cover RU/EN at 320, 390, 768 and 1440px: 144
general-page cases and 88 native-admin/management cases, including limited staff
permissions, keyboard navigation, icons, JavaScript exceptions and page overflow.
Screenshots were inspected on desktop and mobile widths. Physical-device checks
and codec support in Safari remain outside this browser run.

## Night-city theme

VEYRA's night theme uses a subtle animated light background on gallery pages,
varied gallery tile sizes and a still, readable violet-toned administration.
Reduced-motion settings disable ambient movement and reveal transitions. Media
playback, hover previews, permissions and upload handling are unchanged. Grid
thumbnails crop to their frame; the publication page keeps the full image.
