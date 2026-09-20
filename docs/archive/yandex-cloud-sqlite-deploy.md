# Архив: развёртывание SQLite-версии без Docker

**Не используйте для нового развёртывания.** С 20 сентября 2026 года актуальны
[Docker + PostgreSQL](../docker-postgres.md) и [Yandex Cloud](../yandex-cloud-deploy.md).
Ниже сохранена прежняя инструкция для справки; её ручные правки и команды
не следует смешивать с новой конфигурацией.

Проверено по текущему проекту и официальной документации 15 сентября 2026 года.
Это инструкция: облачные ресурсы не создавались, серверные команды не запускались,
а приведённые ниже изменения приложения ещё не внесены.

## 1. Какую схему выбрать

Для первой версии рекомендую **Compute Cloud: одна ВМ с Ubuntu, Nginx, Gunicorn,
SQLite на постоянном диске и SMTP через Postbox**. Вы ранее отменили переход
на PostgreSQL/Docker; эта схема соответствует оставшейся реализации проекта.

Запросы проходят так: браузер → HTTPS/Nginx → Gunicorn → Django → SQLite.
Файлы находятся на диске ВМ; перед их выдачей Nginx проверяет вход через Django.
Регистрационные коды и ссылки восстановления отправляются в Postbox по SMTP.

Моя стартовая оценка ресурсов: Ubuntu 24.04 LTS, 2 vCPU, 2–4 ГБ RAM,
сетевой SSD 30 ГБ, один статический публичный IPv4. Для импорта PDF/XLSX и запаса
по памяти лучше 4 ГБ. Это ориентир для небольшого портала, а не результат нагрузочного
теста. Выберите обычную, не прерываемую ВМ; долю гарантированного CPU учитывайте
при сравнении цен.

| Сервис | Решение для этого сайта |
| --- | --- |
| Compute Cloud | Основной сервер приложения. [Создание Linux-ВМ](https://yandex.cloud/ru/docs/compute/quickstart/quick-create-linux) |
| VPC | Сеть, статический IP и правила доступа. [Группы безопасности](https://yandex.cloud/ru/docs/vpc/operations/security-group-create) |
| Cloud DNS | Необязателен: DNS можно оставить у регистратора домена. [Публичная зона](https://yandex.cloud/ru/docs/dns/operations/zone-create-public) |
| Cloud Postbox | Подтверждение почты и восстановление пароля. [Настройка](https://yandex.cloud/ru/docs/postbox/quickstart) |
| Диски / снимки / Cloud Backup | Постоянные данные и резервные копии. [Диски](https://yandex.cloud/ru/docs/compute/concepts/disk), [Backup](https://yandex.cloud/ru/docs/backup/quickstart/) |
| Managed Service for PostgreSQL | Следующий этап при росте нагрузки; требует подготовки проекта и отдельного переноса. [Начало работы](https://yandex.cloud/ru/docs/managed-postgresql/quickstart) |
| Object Storage | Позже — файлы или отдельная копия backup. Для файлов сайта нужен S3-backend в Django. [Начало работы](https://yandex.cloud/ru/docs/storage/quickstart) |
| Serverless Containers | Другой вариант архитектуры с ревизиями/масштабированием. Для текущих локальных SQLite/media не рекомендую первым шагом. [Модель контейнера](https://yandex.cloud/ru/docs/serverless-containers/concepts/container) |
| Lockbox | Можно добавить для централизованного хранения секретов. [Начало работы](https://yandex.cloud/ru/docs/lockbox/quickstart) |
| Monitoring | Уведомления о проблемах. [Создание алерта](https://yandex.cloud/ru/docs/monitoring/operations/alert/create-alert) |

Kubernetes, балансировщик, отдельный реестр контейнеров и CDN для этого первого
развёртывания не нужны. Certificate Manager понадобится при другой схеме TLS;
здесь сертификат выпускается и обновляется Certbot непосредственно для Nginx.

### Стоимость

Не считайте Yandex Cloud бесплатным аналогом Render Free. Сложите стоимость
ВМ, SSD, IPv4, снимков/backup, исходящего трафика, DNS при использовании и писем.
Рассчитайте 730 часов работы в месяц в [калькуляторе](https://yandex.cloud/ru/prices).
Цена зависит от платформы, доли CPU, региона и тарифа; универсальную сумму здесь
не фиксирую. [Тарификация Compute Cloud](https://yandex.cloud/ru/docs/compute/pricing).

Создайте бюджет с уведомлениями, например на 50%, 80% и 100% выбранной суммы.
Оповещение не следует считать автоматическим отключением всех расходов.
[Как устроены бюджеты](https://yandex.cloud/ru/docs/billing/concepts/budget).

## 2. Что выяснено по коду до развёртывания

1. Сейчас используется `data/db.sqlite3`; загрузки лежат в `data/media/`.
2. Docker-конфигурации нет. Этот документ не требует Docker.
3. В `requirements.txt` нет драйвера PostgreSQL. У закреплённого
   `dj-database-url==1.0.0` нет параметра `conn_health_checks`, который указан
   в настройках проекта. Поэтому **не задавайте DATABASE_URL в этой инструкции**.
4. `static(settings.MEDIA_URL, ...)` работает только в режиме DEBUG; при
   `DEBUG=False` существующие прямые ссылки на фото и вложения требуют отдельной выдачи.
5. Ограничитель отправки писем использует `REMOTE_ADDR`. За обычным Nginx этот адрес
   будет адресом прокси, поэтому нужна небольшая правка из раздела 3.
6. В Git сейчас отслеживаются `.env`, `data/db.sqlite3` и файлы `data/media/`.
   `.gitignore` сам по себе не удаляет ранее отслеживаемые файлы.
7. В `start` есть `makemigrations`; при рабочем деплое выполняйте только `migrate`
   по подготовленным миграциям.

Общие ориентиры Django: [deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/).

## 3. Подготовьте код на своём компьютере

Это обязательные небольшие изменения для конфигурации Nginx ниже. Примеры —
часть инструкции, они не применены к проекту автоматически.

### Уберите рабочие данные из следующих коммитов

Сначала сохраните отдельную резервную копию базы, media и секретов.
Добавьте `data/` в `.gitignore`, затем из корня репозитория выполните:

```shell
git rm --cached -- .env data/db.sqlite3
git rm -r --cached -- data/media
```

Это убирает файлы из индекса Git, но оставляет на компьютере. Историю старых
коммитов команда не очищает. Если туда попадали реальные ключи или пароли,
замените их. Не публикуйте резервную копию базы: в ней есть личные данные и хэши паролей.

### Добавьте проверку доступа к media

Создайте `main/deployment_views.py`:

```python
from django.http import HttpResponse
from django.views.decorators.cache import never_cache


@never_cache
def media_access(request):
    allowed = request.user.is_authenticated and request.user.is_active
    return HttpResponse(status=204 if allowed else 401)
```

В `msu_portal/urls.py` импортируйте `media_access` и добавьте в `urlpatterns`:

```python
from main.deployment_views import media_access

# Внутри urlpatterns:
path('_media_auth/', media_access, name='media_access'),
```

Этот endpoint нужен для внутреннего запроса Nginx. Внешние обращения к нему
будут запрещены через `internal` в конфигурации ниже. Проверка разрешает файлы
всем вошедшим активным пользователям. Если позже материалы должны различаться
по группам или владельцам, потребуется проверка прав на конкретный файл.
[Принцип работы auth_request](https://nginx.org/en/docs/http/ngx_http_auth_request_module.html).

### Исправьте определение IP для лимита писем

В `main/email_auth.py`, внутри `allow_email`, вычисляйте IP так:

```python
client_ip = request.META.get('REMOTE_ADDR', '')
if client_ip in {'127.0.0.1', '::1'}:
    client_ip = request.META.get('HTTP_X_REAL_IP', client_ip)
```

В вызове `take_limit('ip-hour', ...)` замените чтение `REMOTE_ADDR` на `client_ip`.
Это подходит именно для схемы ниже: Gunicorn доступен только на loopback,
а Nginx **перезаписывает** `X-Real-IP`. При добавлении CDN/балансировщика схему
доверия нужно пересмотреть. Gunicorn сам по себе не заменяет `REMOTE_ADDR`
адресом из `X-Forwarded-For`. [Документация Gunicorn](https://gunicorn.org/deploy/).

Сохраните изменения вместе с ранее добавленной email-регистрацией, миграцией
`0008_email_signup_verification.py` и шаблонами в репозитории. Сервер получает
только отправленные коммиты, не локальные несохранённые изменения.

## 4. Создайте облако, сеть и ВМ

Войдите в [консоль Yandex Cloud](https://console.yandex.cloud/), подключите платёжный
аккаунт и создайте каталог, например `msu-portal`. Затем создайте сеть и подсеть
в выбранной доступной зоне. В Compute Cloud создайте ВМ `msu-portal-web`:

- Ubuntu 24.04 LTS, 2 vCPU, 2–4 ГБ RAM, сетевой SSD 30 ГБ.
- Обычная ВМ, не прерываемая.
- Подключение к созданной подсети и публичный IPv4.
- Вход по SSH-ключу; запишите имя Linux-пользователя, далее оно обозначено `ubuntu`.
- При возможности включите защиту ВМ от случайного удаления.

Порядок работы с формой и ключами: [создание Linux-ВМ](https://yandex.cloud/ru/docs/compute/quickstart/quick-create-linux).
Если выбран OS Login, следуйте его способу входа из документации, а не смешивайте
его с обычным логином/ключом из примера ниже.

Назначьте IP статическим, чтобы адрес сайта не менялся после остановки/запуска.
[Преобразование адреса в статический](https://yandex.cloud/ru/docs/vpc/operations/set-static-ip).

Создайте и прикрепите группу безопасности:

| Направление | Порт | Откуда / куда |
| --- | --- | --- |
| Вход | TCP 22 | Только ваш публичный IPv4 `/32` |
| Вход | TCP 80 | `0.0.0.0/0` |
| Вход | TCP 443 | `0.0.0.0/0` |
| Исход | Все | Для первоначальной установки; позднее можно ограничить |

Порты 8000 и 5432 наружу не открывайте. Для SMTP Postbox нужен исходящий TCP 587
или 465. [Создание группы безопасности](https://yandex.cloud/ru/docs/vpc/operations/security-group-create).

### Почему данные теперь сохранятся

Диск ВМ — постоянный облачный ресурс. Перезагрузка ОС и перезапуск Gunicorn
не заменяют его содержимое, как перезапуск эфемерного приложения.
Но удаление ВМ может удалить и загрузочный диск: проверьте `auto-delete`.
Для загрузочного диска изменение автоудаления может требовать CLI/API; не ищите
обязательный переключатель в консоли. Отдельный дополнительный диск с выключенным
автоудалением — дальнейшее улучшение. [Жизненный цикл дисков](https://yandex.cloud/ru/docs/compute/concepts/disk).

## 5. Подключитесь и установите пакеты

На Windows в PowerShell, подставив свой логин/IP:

```powershell
ssh ubuntu@SERVER_IP
```

Если ключ не стандартный, добавьте `-i` с путём к приватному ключу. Все дальнейшие
команды `apt`, `systemctl` и `sudo` выполняются **в SSH-терминале Ubuntu**.

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-dev build-essential git rsync nginx sqlite3 snapd nano
```

Создайте отдельного пользователя приложения и каталоги:

```bash
sudo useradd --system --create-home --home-dir /srv/msu --shell /usr/sbin/nologin msu
sudo chmod 755 /srv/msu
sudo install -d -o msu -g msu -m 755 /srv/msu/releases /srv/msu/shared /srv/msu/shared/data /srv/msu/shared/data/media
sudo install -d -o msu -g msu -m 700 /srv/msu/shared/data/logs /srv/msu/backups
```

Эти команды рассчитаны на новый сервер. Если пользователь/каталоги уже есть,
проверьте их назначение, прежде чем повторять создание.

Структура будет такой:

```text
/srv/msu/
  repository/               исходники из Git
  releases/initial/         первая версия кода + собственное окружение .venv
  current -> releases/...  активная версия
  shared/.env              секреты, не часть версии кода
  shared/data/db.sqlite3    рабочая база
  shared/data/media/        загруженные файлы
  shared/data/logs/         журналы Django
  backups/                 локальные временные резервные копии
```

## 6. Загрузите код и подготовьте первую версию

Переключитесь на пользователя приложения:

```bash
sudo -u msu -H bash
cd /srv/msu
git clone URL_ВАШЕГО_РЕПОЗИТОРИЯ repository
mkdir /srv/msu/releases/initial
rsync -a --exclude='.git/' --exclude='.env*' --exclude='data/' --exclude='.venv*' --exclude='venv/' --exclude='staticfiles/' --exclude='__pycache__/' --exclude='.claude/' --exclude='.vscode/' /srv/msu/repository/ /srv/msu/releases/initial/
cd /srv/msu/releases/initial
test -f manage.py
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
ln -s /srv/msu/shared/data data
ln -s /srv/msu/shared/.env .env
```

Замените `URL_ВАШЕГО_РЕПОЗИТОРИЯ` настоящей ссылкой перед выполнением.
Для закрытого репозитория настройте пользователю `msu` отдельный deploy key
только для чтения. Не вставляйте токен в URL команды.

`test -f manage.py` должен завершиться успешно. В проверенном проекте `manage.py`
лежит в корне репозитория; если вы измените структуру, скорректируйте пути.

## 7. Настройте домен и почту

### Домен

Используйте свой домен, например `portal.example.ru`. Добавьте A-запись `portal`
со значением статического IP. DNS можно оставить у регистратора. Если выбираете
Cloud DNS, создайте публичную зону `example.ru.` и делегируйте её серверам имён,
указанным сервисом. Сначала перенесите существующие записи, особенно почтовые.
[Создание зоны](https://yandex.cloud/ru/docs/dns/operations/zone-create-public),
[создание A-записи](https://yandex.cloud/ru/docs/dns/operations/resource-record-create).

Для первичной проверки используйте TTL 300 секунд. Не создавайте AAAA-запись,
если IPv6 и доступ к сайту через него не настроены.

### Postbox

1. В том же каталоге создайте сервисный аккаунт с ролью `postbox.sender`.
2. Создайте API-ключ с областью действия `yc.postbox.send`.
3. Добавьте домен отправителя в Postbox.
4. Внесите DNS-записи DKIM, которые покажет сервис, и дождитесь успешной проверки.
5. Используйте идентификатор API-ключа как SMTP-логин, его секретную часть как пароль.

Пошагово: [Postbox quickstart](https://yandex.cloud/ru/docs/postbox/quickstart).
Не путайте эти данные с паролем личной Яндекс.Почты. Возможность отправки,
квоты и стоимость проверяются отдельно от создания ВМ.

### Файл .env

Всё ещё под пользователем `msu`:

```bash
umask 077
nano /srv/msu/shared/.env
```

Содержимое, с заменой примеров:

```dotenv
DJANGO_SECRET_KEY=ВАШ_ПОСТОЯННЫЙ_СЛУЧАЙНЫЙ_СЕКРЕТ
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=portal.example.ru
DJANGO_CSRF_TRUSTED_ORIGINS=https://portal.example.ru
PORTAL_PUBLIC_URL=https://portal.example.ru
DJANGO_SECURE_SSL_REDIRECT=True
DATABASE_URL=
RENDER_EXTERNAL_HOSTNAME=

EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=postbox.cloud.yandex.net
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=API_KEY_ID
EMAIL_HOST_PASSWORD=API_KEY_SECRET
DEFAULT_FROM_EMAIL="Учебный портал ВМК МГУ <noreply@example.ru>"
```

Вариант генерации нового Django-секрета: `.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(64))'`.
Не присылайте результат в чат и не коммитьте `.env`. При миграции можно перенести
надёжный секрет со старого сервера; если он был раскрыт в Git, нужен новый.
При его замене пользователям потребуется войти заново.

```bash
chmod 600 /srv/msu/shared/.env
```

Для выдачи статических файлов ниже потребуются права чтения Nginx, поэтому перед
дальнейшей подготовкой кода верните `umask 022`.

## 8. Перенесите базу и загруженные файлы

Выберите источник актуальных данных: локальный компьютер или старый рабочий сервер.
Git-копия SQLite может оказаться устаревшей. Новые изменения с Render не попадут
в локальную копию автоматически. На Render Free нет обычного Shell-доступа;
не перезапускайте старый сервис в надежде получить файлы — сначала нужен доступный
способ экспорта живой базы и media. [Ограничения Render Free](https://render.com/docs/free).

Для SQLite+media снимите копию при остановленных записях. Обычное копирование
активной SQLite без WAL/journal может быть неконсистентным. Если данные актуальны
на локальном компьютере, остановите локальный Django, сохраните отдельно весь
каталог `data`, затем загрузите `db.sqlite3` и `media` через SFTP/`scp` в новый
временный каталог SSH-пользователя, например `/home/ubuntu/msu-import/`.
Не переносите старые логи вместо рабочих данных и не копируйте базу из Git поверх
актуальной. Если WAL/journal существует, сначала сделайте SQLite backup корректным
инструментом, а не передавайте только основной файл.

Выйдите из shell пользователя `msu` командой `exit`. Ниже — первоначальный импорт
на пустой сервер под `ubuntu`, когда Django ещё не запущен:

```bash
sudo test ! -e /srv/msu/shared/data/db.sqlite3
```

Продолжайте только если проверка успешна. Если база уже существует, не перезаписывайте
её: сначала выясните, какая копия актуальна.

```bash
sudo install -o msu -g msu -m 600 /home/ubuntu/msu-import/db.sqlite3 /srv/msu/shared/data/db.sqlite3
sudo rsync -a --chown=msu:msu --chmod=D755,F644 /home/ubuntu/msu-import/media/ /srv/msu/shared/data/media/
sudo -u msu sqlite3 /srv/msu/shared/data/db.sqlite3 'PRAGMA integrity_check;'
```

Ожидаемый ответ последней команды — `ok`. Если нужен совершенно пустой сайт,
пропустите копирование базы и файлов: `migrate` создаст новую SQLite.

Затем:

```bash
sudo -u msu -H bash
umask 022
cd /srv/msu/releases/initial
.venv/bin/python manage.py check
.venv/bin/python manage.py migrate --noinput
chmod 600 /srv/msu/shared/data/db.sqlite3
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py check --deploy
```

Если администратор уже есть в перенесённой базе, пользуйтесь им. Для пустой базы
создайте пользователя через `.venv/bin/python manage.py createsuperuser`, затем
в Django admin (`/admin/`) назначьте ему роль `admin`, если нужна собственная панель
портала: она проверяет `role`, а не только `is_superuser`.
Для пустого сайта сначала добавьте учебные группы в панели: регистрация принимает
только группы, которые уже существуют в базе.

Не игнорируйте ошибки `check --deploy`. Если обсуждаются только HSTS/секреты,
исправляйте конкретную настройку, а не включайте DEBUG ради запуска.

```bash
ln -s /srv/msu/releases/initial /srv/msu/current
exit
```

## 9. Включите автоматический запуск Gunicorn

Под пользователем `ubuntu` откройте `sudo nano /etc/systemd/system/msu-portal.service`:

```ini
[Unit]
Description=MSU Study Portal
After=network-online.target
Wants=network-online.target

[Service]
User=msu
Group=msu
WorkingDirectory=/srv/msu/current
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/srv/msu/current/.venv/bin/gunicorn msu_portal.wsgi:application --bind 127.0.0.1:8000 --workers 1 --threads 4 --timeout 120 --error-logfile -
Restart=on-failure
RestartSec=5
TimeoutStopSec=35
UMask=0022
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Один процесс с четырьмя потоками — стартовый вариант для небольшой SQLite-базы.
Не увеличивайте число процессов как способ исправить `database is locked`.
Для интенсивных одновременных записей нужен PostgreSQL.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now msu-portal
sudo systemctl status msu-portal --no-pager
```

Значение `.env` подхватывает существующий `python-dotenv` через ссылку в каталоге
активной версии. `EnvironmentFile=` не добавляется, чтобы не смешивать два формата
разбора одного файла. [Gunicorn и systemd](https://gunicorn.org/deploy/).

## 10. Настройте Nginx, включая закрытые файлы

Проверьте, что `nginx -V` содержит `--with-http_auth_request_module`.
Если модуль отсутствует, эта конфигурация не запустится: установите сборку Nginx
с этим модулем. Не удаляйте проверку доступа ради запуска.

Откройте `sudo nano /etc/nginx/sites-available/msu-portal` и замените домен:

```nginx
server {
    listen 80;
    server_name portal.example.ru;
    client_max_body_size 50m;

    # Не записываем URL сброса пароля с токенами в access log.
    access_log off;
    error_log /var/log/nginx/msu-portal-error.log warn;

    location /static/ {
        alias /srv/msu/current/staticfiles/;
        expires 1h;
    }

    location = /_media_auth/ {
        internal;
        proxy_pass http://127.0.0.1:8000;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
        proxy_set_header Host $host;
        proxy_set_header Cookie $http_cookie;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /media/ {
        auth_request /_media_auth/;
        alias /srv/msu/shared/data/media/;
        autoindex off;
        add_header Cache-Control "private, no-store" always;
        add_header X-Content-Type-Options "nosniff" always;
        # Пользовательский HTML/SVG не исполняется как страница этого домена.
        types {
            image/jpeg jpg jpeg;
            image/png png;
            image/webp webp;
            image/gif gif;
            application/pdf pdf;
            video/mp4 mp4;
            video/webm webm;
            audio/mpeg mp3;
            audio/ogg ogg;
        }
        default_type application/octet-stream;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 130s;
    }
}
```

Предел 50 МБ относится ко всему запросу; ограничения Django-форм могут быть ниже.
У текущей формы новостей, например, лимит файла 10 МБ.

```bash
sudo ln -s /etc/nginx/sites-available/msu-portal /etc/nginx/sites-enabled/msu-portal
sudo nginx -t
sudo systemctl reload nginx
```

Важно: здесь нет публичного `alias` для `/data/` и всего каталога проекта.
Nginx получает доступ только к статике и к media после проверки авторизации.
Механизм проверки: [auth_request](https://nginx.org/en/docs/http/ngx_http_auth_request_module.html).

## 11. Подключите HTTPS

Сначала убедитесь, что A-запись домена указывает на ВМ и порт 80 доступен снаружи.
Затем установите Certbot через snap:

```bash
sudo snap install --classic certbot
sudo /snap/bin/certbot --nginx -d portal.example.ru
sudo /snap/bin/certbot renew --dry-run
```

Certbot добавит TLS в подходящий server block Nginx. Выберите перенаправление
HTTP на HTTPS. Инструкции: [Ubuntu: получение TLS-сертификатов](https://ubuntu.com/server/docs/how-to/security/obtain-tls-certificates/),
[Certbot для Nginx](https://certbot.eff.org/instructions?os=snap&ws=nginx).

До выдачи сертификата браузер может получать перенаправление Django на пока
неработающий HTTPS — это ожидаемо при `DJANGO_SECURE_SSL_REDIRECT=True`.
Если выпуск сертификата не проходит, сначала проверяйте DNS и порт 80.

Не используйте HTTP для рабочего входа: у проекта secure cookies. Если появляется
цикл перенаправлений после включения HTTPS, проверьте `X-Forwarded-Proto` и
`SECURE_PROXY_SSL_HEADER`, а не отключайте защиту вслепую.

## 12. Проверьте сайт перед переключением пользователей

- Публичная главная, кафедры и расписание открываются по HTTPS.
- `/login/` позволяет войти старым пользователям.
- Форма регистрации отправляет настоящий код; без него аккаунт не создаётся.
- Ссылка восстановления ведёт на новый домен, новый пароль работает.
- После входа открываются старые вложения, PDF и фото профиля.
- Прямая ссылка `/media/...` без входа возвращает 401, а не файл.
- Обычный пользователь не попадает в административную панель.
- Новая запись расписания и новое вложение сохраняются после `sudo systemctl restart msu-portal`.
- После плановой перезагрузки ВМ сайт запускается автоматически и данные остаются.

Перед окончательным переездом прекратите записи на старом сайте, перенесите финальную
копию данных и только затем переключите домен. Две независимо изменяемые SQLite-базы
сами не объединятся.

## 13. Обновление кода без сброса данных

Не обновляйте приложение копированием старой `db.sqlite3` из репозитория.
Для каждой версии создавайте новый каталог; `data` и `.env` остаются общими.
Команды ниже выполняйте по очереди, останавливаясь при любой ошибке.

Под пользователем `msu`:

```bash
cd /srv/msu/repository
git pull --ff-only
RELEASE="/srv/msu/releases/$(date +%Y%m%d-%H%M%S)"
mkdir "$RELEASE"
rsync -a --exclude='.git/' --exclude='.env*' --exclude='data/' --exclude='.venv*' --exclude='venv/' --exclude='staticfiles/' --exclude='__pycache__/' --exclude='.claude/' --exclude='.vscode/' /srv/msu/repository/ "$RELEASE/"
ln -s /srv/msu/shared/data "$RELEASE/data"
ln -s /srv/msu/shared/.env "$RELEASE/.env"
cd "$RELEASE"
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py check --deploy
.venv/bin/python manage.py collectstatic --noinput
readlink /srv/msu/current
printf '%s\n' "$RELEASE"
```

Запишите старый путь и новый путь. Вернитесь в shell `ubuntu` через `exit`.
Далее — короткое окно обслуживания:

1. Остановите приложение: `sudo systemctl stop msu-portal`.
2. Сделайте backup по разделу 14.
3. Выполните миграции **новой** версии:
   `sudo -u msu НОВЫЙ_ПУТЬ/.venv/bin/python НОВЫЙ_ПУТЬ/manage.py migrate --noinput`.
4. При успехе переключите ссылку:
   `sudo -u msu ln -sfn НОВЫЙ_ПУТЬ /srv/msu/current`.
5. Запустите приложение: `sudo systemctl start msu-portal`.
6. Проверьте вход, формы, файлы и журналы. Nginx читает статику через `current`.

Миграции выполняются до запуска новой версии, `makemigrations` на сервере не нужен.
Если миграция завершилась ошибкой, не переключайте ссылку и сначала выясните,
какая часть схемы успела измениться. Откат только ссылки не всегда совместим
с уже изменённой базой; для отката данных нужна согласованная резервная копия.
Восстановление старой базы после появления новых записей потеряет эти записи.

## 14. Резервные копии и обслуживание

Для небольшой SQLite-инсталляции перед обновлением остановите сервис и сделайте
согласованную копию БД и файлов. Сначала `sudo systemctl stop msu-portal`, затем:

```bash
sudo -u msu -H bash
umask 077
BACKUP="/srv/msu/backups/$(date +%Y%m%d-%H%M%S)"
mkdir "$BACKUP"
sqlite3 /srv/msu/shared/data/db.sqlite3 ".backup '$BACKUP/db.sqlite3'"
tar -czf "$BACKUP/media.tar.gz" -C /srv/msu/shared/data media
sqlite3 "$BACKUP/db.sqlite3" 'PRAGMA integrity_check;'
exit
```

После проверки и завершения обслуживания запустите `sudo systemctl start msu-portal`.
Если сбой возник в процессе копирования, проверьте статус и не оставляйте сервис
остановленным случайно.

Копия на том же диске помогает при неудачном обновлении, но не при потере диска.
Добавьте [Cloud Backup](https://yandex.cloud/ru/docs/backup/quickstart/) или
[снимки диска](https://yandex.cloud/ru/docs/compute/operations/disk-control/create-snapshot).
Для простого консистентного снимка SQLite остановите записи на время снимка.
Отдельно сохраните `.env` в защищённом месте. Проверяйте восстановление на другой
ВМ. Назначьте срок хранения копий: они тоже занимают место и могут тарифицироваться.

Периодически выполняйте под `msu` из `/srv/msu/current`:

```bash
.venv/bin/python manage.py clearsessions
.venv/bin/python manage.py cleanup_email_auth
```

Для расписания используйте systemd timer/cron на ВМ: `cleanup_email_auth` раз в час,
`clearsessions` ежедневно. При переносе команды в cron задайте абсолютные пути
и рабочий каталог. Сам этот документ расписание не устанавливает.

Наблюдайте за CPU, памятью, заполнением диска и доступностью HTTPS. Метрики гостевой
ОС могут потребовать агента; наличие графика CPU не означает, что контролируется
свободное место внутри файловой системы. [Создание алерта](https://yandex.cloud/ru/docs/monitoring/operations/alert/create-alert).

## 15. Быстрая диагностика

```bash
sudo systemctl status msu-portal --no-pager
sudo journalctl -u msu-portal -n 100 --no-pager
sudo tail -n 100 /var/log/nginx/msu-portal-error.log
sudo nginx -t
df -h
free -h
```

| Симптом | Где искать причину |
| --- | --- |
| 502 | Gunicorn не запущен; ошибка зависимостей, миграции или чтения `.env` |
| 400 / Invalid HTTP_HOST | `DJANGO_ALLOWED_HOSTS`, правильность домена |
| 403 CSRF | HTTPS-домен в `DJANGO_CSRF_TRUSTED_ORIGINS`, заголовки прокси |
| 404 на CSS | `collectstatic`, путь `staticfiles`, права Nginx |
| 401 на media после входа | Cookie, `_media_auth`, активность пользователя, один и тот же домен |
| 500 на media | Отсутствует endpoint `_media_auth` либо его ответ не 2xx/401/403 |
| Нет писем | Не оставлен ли console backend, SMTP-ключи, DKIM, порт 587 и лимит отправки |
| database is locked | Конкурентные записи в SQLite; планировать переход на PostgreSQL |
| Данные исчезли после обновления | Подменили `data` или рабочую базу версией из Git |

В текущем проекте часть логов Django пишет в `/srv/msu/shared/data/logs/`.
Они также полезны при диагностике, но не публикуйте их целиком вместе с личными данными.

## 16. Когда переходить на PostgreSQL и Object Storage

Когда одновременных записей станет много или понадобятся несколько серверов:

1. Подготовить драйвер PostgreSQL, совместимую версию `dj-database-url` и команды переноса.
2. Создать Managed PostgreSQL без публичного доступа, в сети приложения;
   разрешить подключения от ВМ через группу безопасности и настроить TLS по
   [официальной инструкции](https://yandex.cloud/ru/docs/managed-postgresql/quickstart).
3. Перенести и проверить данные на отдельной базе, затем выполнить контролируемое
   переключение с остановленными записями.
4. Для Object Storage добавить S3-backend, закрытый bucket и выдачу файлов с
   проверкой прав. Текущий проект ещё не готов переключиться простым добавлением
   ключей в `.env`.

До этого обычная ВМ с постоянным диском решает исходную проблему потери SQLite
и файлов при перезапусках. Отказоустойчивость и резервное копирование — отдельные
задачи: одна ВМ остаётся одной точкой отказа.
