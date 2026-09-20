# Docker + PostgreSQL: запуск и перенос данных

Справочник актуальных переменных и правил исключения файлов: [окружение](environment.md).

**В текущей локальной рабочей копии перенос уже выполнен 20.09.2026.**
Повторять импорт не нужно: PostgreSQL заполнена, `.env.docker` создан,
сайт доступен на http://127.0.0.1:8000 после запуска Docker Desktop и
`docker compose --env-file .env.docker up -d`.
Исходная `data/db.sqlite3` сохранена без изменений. Дальнейшие данные записываются
в PostgreSQL при работе через Docker. На Yandex Cloud сайт пока не опубликован.

## 1. Что изменилось

- `web`: Django + Gunicorn, Python 3.12; рабочий процесс от UID 10001, не root.
- `db`: PostgreSQL 17, без публичного порта; постоянный том `msu-portal_postgres_data`.
- `data/media`: файлы на диске хоста, не внутри пересоздаваемого контейнера.
- `staticfiles`: собранные CSS/JS, на сервере их отдаёт Nginx.
- `.env.docker`: отдельные секреты Docker. Старый `.env` не используется в образе.
- Nginx и Certbot работают **на ВМ**, не в контейнере: проще подключить HTTPS.
- Миграции запускаются отдельной командой, а не при каждом перезапуске сервера.

Локальный `python manage.py runserver` без новых переменных всё ещё использует
SQLite. Не ведите одновременно две рабочие базы после переноса: выберите Docker.
Перенос локальной SQLite не переносит автоматически более свежие данные с Render.

## 2. Локальный запуск в Windows

Запустите Docker Desktop с Linux containers. Выполняйте команды из корня проекта.
Для Linux замените `python` на `python3`, если нужно.

```powershell
python docker/init_env.py
docker compose --env-file .env.docker config --quiet
docker compose --env-file .env.docker build web
docker compose --env-file .env.docker up -d db
docker compose --env-file .env.docker run --rm web python manage.py migrate --noinput
```

Если `.env.docker` уже создан, первая команда откажется его перезаписывать —
используйте существующий файл. Секреты генерируются случайно, не выводятся в чат.
Не публикуйте вывод `docker compose config` без `--quiet`: он содержит пароли.

### Перенос существующей SQLite

Остановите старый `runserver` и все записи в SQLite. Не создавайте суперпользователя
в PostgreSQL перед импортом — целевая база должна быть пустой, кроме миграционных
справочников. Команда откажется объединять её с существующими пользователями.

```powershell
docker compose --env-file .env.docker stop web
docker compose --env-file .env.docker run --rm web python manage.py migrate_from_sqlite /app/data/db.sqlite3 --dry-run
docker compose --env-file .env.docker run --rm web python manage.py migrate_from_sqlite /app/data/db.sqlite3
```

При ненулевом коде выхода остановитесь и разберите ошибку, а не выполняйте следующие
команды. `--dry-run` проверяет SQLite и возможность экспорта, но не заменяет пробную
загрузку в PostgreSQL: она строже проверяет типы и длины строк.

Импорт создаёт приватный каталог `data/backups/sqlite-import-...` с согласованной
копией SQLite и JSON-экспортом. Исходный файл не изменяется. Сохраняются ID, хеши
паролей, роли, связи, группы, новости, расписание и имена файлов. Файлы уже доступны
через общую `data/media`; при переносе на другую машину скопируйте её отдельно.
Импорт выполняется одной транзакцией с проверкой количества строк и внешних ключей.
Последовательности ID обновляются Django. Повторный импорт в заполненную базу запрещён.

Сеансы входа, незавершённые регистрации и лимиты писем не переносятся: пользователи
войдут заново, а незавершённую регистрацию начнут сначала. Пароли аккаунтов остаются.
Экспорт содержит персональные данные и хеши паролей — не отправляйте его в Git или чат.

Если исходная SQLite от старой версии и команда сообщает о незавершённых миграциях:
работайте только с её отдельной согласованной копией. Например, поместите копию
в `data/import/source.sqlite3`, затем обновите **копию**:

```powershell
docker compose --env-file .env.docker run --rm -e DATABASE_ENGINE=sqlite -e SQLITE_PATH=/app/data/import/source.sqlite3 web python manage.py migrate --noinput
docker compose --env-file .env.docker run --rm web python manage.py migrate_from_sqlite /app/data/import/source.sqlite3
```

Не копируйте работающую SQLite обычным файловым копированием: при WAL часть данных
может находиться в другом файле. Остановите все процессы записи или используйте SQLite backup API.

### Запуск после импорта

```powershell
docker compose --env-file .env.docker run --rm web python manage.py collectstatic --noinput
docker compose --env-file .env.docker up -d web
docker compose --env-file .env.docker ps
```

Откройте http://127.0.0.1:8000. Локально `DEBUG=True`, письма выводятся в журнал
`docker compose --env-file .env.docker logs --tail=100 web`.
Это **не отправка реальных писем**. Не публикуйте журнал с кодами и ссылками.

Для полностью новой базы, **вместо импорта**, выполните `createsuperuser` через
`docker compose --env-file .env.docker run --rm web python manage.py createsuperuser`.
Для пользовательской админ-панели дополнительно назначьте аккаунту роль `admin`
в `/admin/`. Создайте учебные группы до открытия регистрации.

## 3. Сервер Yandex Cloud

Создайте ВМ по [облачной инструкции](yandex-cloud-deploy.md). Ориентир: Ubuntu 24.04,
2 vCPU / 4 ГБ, SSD 30 ГБ; открыты только 22 с вашего IP, 80/443 публично.

Установите Docker Engine и Compose plugin из
[официального репозитория Docker](https://docs.docker.com/engine/install/ubuntu/).
На ВМ ниже используйте `sudo docker`, если у вашего пользователя нет прав Docker.
Членство в группе `docker` даёт практически root-доступ — выдавайте только доверенным
администраторам. Для простоты команды ниже предполагают, что доступ уже настроен.

```bash
sudo apt update
sudo apt install -y git nginx python3 nano snapd
sudo systemctl enable --now docker nginx
sudo install -d -o ubuntu -g ubuntu -m 755 /srv/msu/portal
git clone <URL_ВАШЕГО_РЕПОЗИТОРИЯ> /srv/msu/portal
cd /srv/msu/portal
python3 docker/init_env.py
nano .env.docker
```

Перед загрузкой кода убедитесь, что секреты, база и файлы не отслеживаются Git:
`git ls-files .env data`. `.gitignore` сам по себе не удаляет уже отслеживаемые файлы.
При необходимости используйте `git rm --cached .env data/db.sqlite3` и
`git rm -r --cached data/media` и сохраните изменение в коммите. Это не удаляет
локальные рабочие файлы, но не очищает старую историю. Реальные опубликованные
пароли/ключи нужно перевыпустить. Не кладите токен репозитория в URL командной строки.

В этой рабочей копии `.env`, SQLite и два ранее отслеживаемых вложения уже сняты
с отслеживания (изменение индекса Git); файлы на диске сохранены. Коммит/публикация
автоматически не выполнялись.

В `.env.docker` сохраните сгенерированные `POSTGRES_*` и `DJANGO_SECRET_KEY`, а
веб-параметры поменяйте на свои:

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
EMAIL_HOST_USER=API_KEY_ID
EMAIL_HOST_PASSWORD=API_KEY_SECRET
DEFAULT_FROM_EMAIL=Учебный портал ВМК МГУ <noreply@portal.example.ru>
```

`DJANGO_TRUST_PROXY_CLIENT_IP=True` безопасен только при доступе к web через доверенный
Nginx, который **перезаписывает** `X-Real-IP`. Compose публикует порт только на
`127.0.0.1`. Не меняйте его на `0.0.0.0`, не прокидывайте входящий заголовок как есть.
Параметр нужен, чтобы почтовый лимит применялся отдельно к каждому посетителю.

Postbox: [создание отправителя](https://yandex.cloud/ru/docs/postbox/quickstart),
[SMTP и API-ключ](https://yandex.cloud/ru/docs/postbox/operations/send-email).
Подтвердите домен через DKIM-записи из консоли; роль сервисного аккаунта
`postbox.sender`, scope ключа `yc.postbox.send`. Отправитель должен быть подтверждён.

```bash
chmod 600 .env.docker
mkdir -p data/media data/logs data/backups staticfiles
```

Перед первым импортом загрузите согласованную SQLite в `data/db.sqlite3` и все
вложения в `data/media`. Не используйте случайную старую базу из Git вместо рабочей.
Заморозьте записи на прежнем сайте перед окончательным переносом. Возможности экспорта
Render зависят от тарифа; не перезапускайте его до получения нужных данных.

Права для контейнера и чтения media/static через Nginx (проверьте, что вы в
`/srv/msu/portal`, а `data` и `staticfiles` — именно каталоги этого проекта):

```bash
sudo chown -R 10001:10001 /srv/msu/portal/data /srv/msu/portal/staticfiles
sudo find /srv/msu/portal/data/media -type d -exec chmod 755 {} +
sudo find /srv/msu/portal/data/media -type f -exec chmod 644 {} +
sudo chmod 755 /srv/msu/portal/data /srv/msu/portal/staticfiles
sudo chmod 700 /srv/msu/portal/data/backups
```

Выполните команды сборки, `up -d db`, `migrate`, проверочного/настоящего импорта и
`collectstatic` из раздела 2. Затем `up -d web`. До HTTPS редирект на ещё не настроенный
порт 443 ожидаем; не используйте это как повод включать DEBUG на сервере.

## 4. Nginx и HTTPS

Домен A-записью уже должен указывать на статический IP ВМ. Замените домен в копии
конфигурации, а путь оставьте `/srv/msu/portal` либо согласованно замените его:

```bash
sudo cp docker/nginx.conf /etc/nginx/sites-available/msu-portal
sudo nano /etc/nginx/sites-available/msu-portal
sudo ln -s /etc/nginx/sites-available/msu-portal /etc/nginx/sites-enabled/msu-portal
sudo nginx -t
sudo systemctl reload nginx
sudo snap install --classic certbot
sudo /snap/bin/certbot --nginx -d portal.example.ru
sudo /snap/bin/certbot renew --dry-run
```

При повторной настройке не создавайте второй symlink. Если `nginx -t` сообщает,
что `auth_request` неизвестен, используйте сборку Nginx с этим модулем — не убирайте
проверку доступа. [Документация auth_request](https://nginx.org/en/docs/http/ngx_http_auth_request_module.html),
[HTTPS на Ubuntu](https://ubuntu.com/server/docs/how-to/security/obtain-tls-certificates/).

В production `/media/` доступна только активным вошедшим пользователям. Неизвестный
пользователь получает 401, HTML/SVG-файлы выдаются как загрузка, а не выполняются.
Права на конкретную группу/объект здесь не добавлены: сохранена общая политика
доступа к вложениям для зарегистрированных пользователей. Локальный DEBUG-сервер
не является защищённым production-сервером для файлов.

```bash
docker compose --env-file .env.docker exec web python manage.py check --deploy
docker compose --env-file .env.docker ps
```

Проверьте регистрацию с настоящим письмом, вход, сброс пароля, редактирование
расписания, загрузку/скачивание файлов, анонимный отказ `/media/`, мобильные страницы.
Только после этого переключайте пользователей со старого сайта.

## 5. Обновления без сброса данных

Не меняйте имя Compose-проекта `msu-portal`: оно определяет имя тома PostgreSQL.
Не меняйте major-версию `postgres:17-bookworm` без отдельной процедуры обновления БД.

```bash
cd /srv/msu/portal
python3 docker/backup.py
git pull --ff-only
docker compose --env-file .env.docker build web
docker compose --env-file .env.docker stop web
docker compose --env-file .env.docker run --rm web python manage.py migrate --noinput
docker compose --env-file .env.docker run --rm web python manage.py collectstatic --noinput
docker compose --env-file .env.docker up -d web
docker compose --env-file .env.docker ps
```

Выполняйте команды последовательно, проверяя успешное завершение. На время миграции
сайт недоступен. При ошибке миграции не продолжайте автоматически и не импортируйте
старую SQLite поверх PostgreSQL. Для точной точки отката перед миграцией остановите
web и сделайте ещё одну резервную копию: между первой копией и остановкой были записи.
Откат версии кода не всегда откатывает схему БД.

Обычный перезапуск: `docker compose --env-file .env.docker restart web`.
После изменения `.env.docker` нужен `docker compose --env-file .env.docker up -d --force-recreate web`;
обычный `restart` не обновляет окружение.

**Нельзя использовать `docker compose down -v`, удалять том `msu-portal_postgres_data`
или делать `docker volume prune`, не проверив последствия.** `down` без `-v`
сохраняет том, но останавливает сайт и БД. Вложения не должны храниться только в образе.
Изменение `POSTGRES_PASSWORD` в env не меняет пароль уже созданной базы: ротация
требует согласованного изменения пароля роли PostgreSQL и настроек приложения.

## 6. Резервные копии и восстановление

```bash
python3 docker/backup.py
```

Скрипт кратко останавливает web, делает `pg_dump -Fc`, проверяет читаемость архива,
упаковывает media и запускает web обратно, если он работал. Полный набор содержит
`postgres.dump`, `media.tar.gz` и маркер `COMPLETE`. Набор без `COMPLETE` считайте
неполным. Другие процессы, пишущие в БД/media, тоже должны быть остановлены.
Обеспечьте запас места. Пароли и `.env.docker` сохраняйте отдельно в защищённом месте.

На Linux для доступа к файлам UID 10001 скрипт может потребовать
`sudo python3 docker/backup.py`. На Windows запускайте из среды с доступом к Docker.
Копируйте архив на другой диск/ВМ или приватное хранилище. Бэкап на том же SSD
не защищает от его потери. Автоматическое расписание не включено: настройте cron
или systemd timer после проверки прав и тестового восстановления.

Восстановление проверяйте на отдельной ВМ или другом Compose-проекте с новым томом.
Не запускайте `migrate` в пустой БД перед восстановлением полного PostgreSQL-дампа.
Ниже `BACKUP` — путь к выбранному полному набору; команды выполняются в Bash:

```bash
docker compose --env-file .env.docker up -d db
docker compose --env-file .env.docker cp BACKUP/postgres.dump db:/tmp/portal.dump
docker compose --env-file .env.docker exec db sh -c 'pg_restore --single-transaction --exit-on-error --no-owner --no-acl -U "$POSTGRES_USER" -d "$POSTGRES_DB" /tmp/portal.dump'
tar -xzf BACKUP/media.tar.gz -C data
sudo chown -R 10001:10001 /srv/msu/portal/data/media
docker compose --env-file .env.docker run --rm web python manage.py migrate --noinput
docker compose --env-file .env.docker run --rm web python manage.py collectstatic --noinput
docker compose --env-file .env.docker up -d web
```

Распаковывайте только собственный доверенный архив в пустой каталог media;
не перезаписывайте рабочую базу и файлы этими командами. Проверьте вход и вложения.
Архив в `/tmp/portal.dump` внутри контейнера после проверки можно удалить.
Официально: [pg_dump](https://www.postgresql.org/docs/17/backup-dump.html),
[pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html).

## 7. Диагностика и тесты

```bash
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker logs --tail=100 web db
docker compose --env-file .env.docker run --rm web python manage.py check
docker compose --env-file .env.docker run --rm web python manage.py makemigrations --check --dry-run
docker compose --env-file .env.docker run --rm web python manage.py test main schedule materials --noinput
```

Тесты создают отдельную `test_msu_portal`; не запускайте их на перегруженной рабочей
ВМ. `main.test_postgres_import` проверяет настоящий перенос SQLite → PostgreSQL,
связи, права, пароли, автоинкремент и откат невалидного импорта. На SQLite эти тесты
пропускаются. Встроенная роль контейнера БД административная; для более строгого
production-разделения выделите отдельные роли приложения, миграций и резервных копий.

- 502: проверьте контейнер web, занятый порт 8000 и журналы Nginx.
- 400/CSRF 403: проверьте домен, HTTPS и `DJANGO_CSRF_TRUSTED_ORIGINS`.
- Нет CSS: выполнен ли `collectstatic`, читает ли Nginx `staticfiles`.
- Нет писем: SMTP backend, ключи Postbox, подтверждённый отправитель, исходящий 587.
- БД пуста после изменения каталога/команд: проверьте имя проекта/тома, не импортируйте
  повторно до выяснения, где находится рабочий том.

Периодически запускайте `cleanup_email_auth` и `clearsessions` через `compose exec web`.
На сервере не включайте DEBUG для диагностики и не отправляйте секреты/дампы в чат.
