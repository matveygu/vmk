# Настройки окружения и ignore-файлы

Команды выполняются из `C:\Users\engtc_pbk5w0m\CLionProjects\vmk`.

## Какой файл редактировать

| Файл | Назначение |
| --- | --- |
| `.env.docker` | Текущий сайт в Docker с PostgreSQL; этот файл нужен и на ВМ Yandex Cloud |
| `.env` | Отдельный локальный `python manage.py runserver` с SQLite, для разработки |
| `.env.docker.example`, `.env.example` | Публичные шаблоны без паролей |

После переноса данных используйте Docker. Локальный `runserver` с `.env` не видит
изменения PostgreSQL и не должен становиться второй рабочей копией сайта.
Настройки процесса имеют приоритет над `.env`. Django читает `.env` только из корня
этого проекта, не ищет его в родительских каталогах. В Docker-образ `.env` не попадает.
Compose сам задаёт PostgreSQL и адрес `db`; публичный порт базы не открыт.

Действующие файлы уже приведены к шаблонам, пароли и ключи сохранены.
Резервная копия предыдущих файлов:
`data/backups/env-20260920-134140-2_ud1tny/`.
Она содержит секреты — не отправляйте её в Git, чат или общедоступное хранилище.
На Windows доступ регулируется ACL каталога; на Linux скрипт создаёт приватные файлы.

## Создание и обновление

Для **нового** проекта, где соответствующего файла ещё нет:

```powershell
python docker/init_env.py          # .env.docker + случайные секреты
python docker/init_env.py --local  # .env + случайный ключ Django
```

Существующие файлы эти команды никогда не перезаписывают.
Для безопасного выравнивания существующих файлов по обновлённым шаблонам:

```powershell
python docker/refresh_env.py          # Только проверка
python docker/refresh_env.py --apply  # Резервная копия, затем форматирование
```

Нужен `python-dotenv` из `requirements.txt`. Скрипт сохраняет существующие значения,
включая кавычки и дополнительные настройки. При неоднозначном синтаксисе, дубликатах
или изменении значения из-за `${...}` отказывается от операции. Удаляет только
перечисленные в скрипте устаревшие параметры Google Sheets/планировщика и Render.
После ручного редактирования `.env.docker`:

```powershell
docker compose --env-file .env.docker config --quiet
docker compose --env-file .env.docker up -d --no-deps --force-recreate web
docker compose --env-file .env.docker ps
```

Если меняли код, сначала выполните `docker compose --env-file .env.docker build web`.
Простой `restart` не подхватывает изменённое окружение контейнера.
Не публикуйте обычный `docker compose config`: без `--quiet` он показывает секреты.

**Не меняйте `POSTGRES_PASSWORD` только в файле:** пароль в уже созданном томе
PostgreSQL от этого не изменится и сайт потеряет подключение. Ротация требует
согласованной смены пароля в самой базе. Не используйте `down -v` для исправления:
эта команда удаляет том с данными. Не меняйте также имя Compose-проекта `msu-portal`.

## Перед запуском на Yandex Cloud

Текущие настройки намеренно локальные: `DEBUG=True`, HTTP и письма в консоль.
После настройки домена, Nginx и HTTPS измените **существующий** `.env.docker`:

```dotenv
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=portal.example.ru
DJANGO_CSRF_TRUSTED_ORIGINS=https://portal.example.ru
DJANGO_SECURE_SSL_REDIRECT=True
DJANGO_TRUST_PROXY_CLIENT_IP=True
PORTAL_PUBLIC_URL=https://portal.example.ru
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=postbox.cloud.yandex.net
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=YOUR_SMTP_LOGIN
EMAIL_HOST_PASSWORD=YOUR_SMTP_PASSWORD
DEFAULT_FROM_EMAIL=Учебный портал ВМК МГУ <noreply@portal.example.ru>
```

Замените пример домена и SMTP-реквизиты своими. Ключ Django должен быть случайным,
приватным; действующий ключ не меняйте без необходимости — смена сбросит сеансы.
`DJANGO_TRUST_PROXY_CLIENT_IP=True` допустим только за Nginx из проекта,
который перезаписывает заголовки, при привязке порта приложения к `127.0.0.1`.
TLS и SSL для SMTP нельзя включать одновременно. После применения:

```powershell
docker compose --env-file .env.docker run --rm web python manage.py check --deploy
```

Полный порядок: [Docker и PostgreSQL](docker-postgres.md),
[Yandex Cloud](yandex-cloud-deploy.md), [настройка почты](email-setup.md).

## Журналы и проверка работоспособности

`LOG_LEVEL=INFO` управляет уровнем Django и приложения. Журналы идут в стандартный
поток и доступны через `docker compose --env-file .env.docker logs --tail=100 web`.
Docker ограничивает размер: три файла по 10 МБ на контейнер. Это исключает
конкурирующую ротацию одних файлов несколькими Gunicorn-процессами. Старые файлы
`data/logs` не удалены, но новые сообщения туда больше не пишутся.
Логи могут содержать диагностические данные, а при консольной почте — коды входа
и ссылки восстановления. Не публикуйте их; в production используйте SMTP.

Healthcheck обращается к уже запущенному HTTP-worker и проверяет `SELECT 1` в БД.
Он больше не загружает отдельный Django-процесс каждые 30 секунд. Ответ — только
`ok` (200) или `unavailable` (503), без реквизитов, без кэширования. В Nginx
внешний доступ к `/_health/` закрыт. Команда `manage.py check_database` остаётся
доступной для ручной диагностики. Здоровье контейнера не проверяет доставку почты,
работу публичного DNS/HTTPS или полноту миграций; Docker не перезапускает контейнер
только из-за статуса unhealthy.

## Что исключено из Git и Docker

Секретные `.env*`, базы, дампы, резервные копии, загрузки, логи, приватные ключи,
виртуальные окружения, кэши и настройки редакторов. В Git разрешены только два
публичных `.env*.example`. В образ не попадают даже примеры и документация.
Исходники `static/`, миграции и тесты остаются доступны для сборки и проверки.
В частности, справочник `static/data/faculties.json` больше не скрывается ошибочным
общим правилом `data/`: это необходимый публичный файл приложения.

Ignore-правила не удаляют файлы из уже существующей истории Git. Если секреты
когда-либо публиковались, их нужно отдельно отозвать и заменить.
