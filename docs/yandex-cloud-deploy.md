# Yandex Cloud: Docker + PostgreSQL

Актуальная схема проекта, 20 сентября 2026 года:
браузер → Nginx/HTTPS на ВМ → Django/Gunicorn в Docker → PostgreSQL 17 в Docker.
Почта: Cloud Postbox по SMTP. Загруженные файлы: постоянный диск ВМ.

Это подготовленная конфигурация, а не уже созданная облачная инфраструктура.
Все команды приложения и порядок переноса находятся в [основной инструкции](docker-postgres.md).
Прежний вариант SQLite без Docker сохранён только в [архиве](archive/yandex-cloud-sqlite-deploy.md).

## 1. Облако и сервер

1. Откройте [консоль Yandex Cloud](https://console.yandex.cloud/), создайте облако,
   платёжный аккаунт и каталог. Не рассчитывайте на постоянный бесплатный сервер.
2. Создайте обычную, не прерываемую ВМ с Ubuntu 24.04 LTS по
   [официальной инструкции](https://yandex.cloud/ru/docs/compute/quickstart/quick-create-linux).
   Начальный ориентир: 2 vCPU, 4 ГБ RAM, SSD 30 ГБ. Это оценка, а не результат нагрузочного теста.
3. Добавьте свой публичный SSH-ключ. Приватный ключ никому не передавайте.
4. Закрепите [статический публичный IP](https://yandex.cloud/ru/docs/vpc/operations/set-static-ip).
5. В [группе безопасности](https://yandex.cloud/ru/docs/vpc/operations/security-group-create)
   разрешите входящие TCP 22 только со своего IP, 80 и 443 — из интернета.
   Порты 8000 и 5432 не открывайте. Исходящие соединения нужны для образов,
   обновлений, DNS и SMTP 587.
6. Посчитайте ВМ, диск, IPv4, исходящий трафик и резервные копии в
   [калькуляторе](https://yandex.cloud/ru/prices), настройте
   [бюджетные уведомления](https://yandex.cloud/ru/docs/billing/concepts/budget).
   Уведомление не является гарантированным ограничителем расходов.

## 2. Docker и приложение

Подключитесь `ssh ubuntu@IP`. Установите Docker Engine и Compose по
[инструкции Docker для Ubuntu](https://docs.docker.com/engine/install/ubuntu/).
На ВМ нужен Docker Engine, а не Docker Desktop. Установите также Nginx, Git,
Python 3, nano и snapd. Затем выполните серверные разделы
[инструкции проекта](docker-postgres.md).

Фиксированный путь для готовой конфигурации: `/srv/msu/portal`.
Не запускайте старую systemd-службу Gunicorn одновременно с Docker на порту 8000.

## 3. Домен, HTTPS и почта

У регистратора создайте DNS A-запись домена на IP сервера. Cloud DNS необязателен;
при его использовании смотрите [создание публичной зоны](https://yandex.cloud/ru/docs/dns/operations/zone-create-public)
и [добавление записи](https://yandex.cloud/ru/docs/dns/operations/resource-record-create).
При смене DNS-серверов сохраните существующие MX/TXT-записи почты.

Готовая конфигурация Nginx: `docker/nginx.conf`. Подстановка домена, получение
сертификата Let's Encrypt и HTTPS-параметры Django описаны в основной инструкции.
Не включайте боевой приём регистраций до проверки HTTPS и отправки почты.

Для Postbox создайте сервисный аккаунт с ролью `postbox.sender`, API-ключ
с областью действия `yc.postbox.send` и подтвердите адрес/домен отправителя
через записи из консоли. Не используйте пароль от личной почты.

- [Начало работы с Postbox](https://yandex.cloud/ru/docs/postbox/quickstart).
- [SMTP: сервер, порты и учётные данные](https://yandex.cloud/ru/docs/postbox/operations/send-email).
- [Настройка почты в проекте](email-setup.md).

## 4. Сохранность и обслуживание

PostgreSQL находится в именованном Docker-томе `msu-portal_postgres_data`;
файлы — в `/srv/msu/portal/data/media`. Пересборка web-контейнера их не удаляет.
Но удаление тома или диска ВМ уничтожает данные. У загрузочного диска проверьте
настройку удаления вместе с ВМ — [описание дисков](https://yandex.cloud/ru/docs/compute/concepts/disk).

Используйте `docker/backup.py`, проверяйте восстановление и копируйте архивы
на отдельное хранилище. Локальный каталог `data/backups` не защищает от потери ВМ.
Дополнительно доступны [Cloud Backup](https://yandex.cloud/ru/docs/backup/quickstart/)
и [снимки дисков](https://yandex.cloud/ru/docs/compute/operations/disk-control/create-snapshot).
Задачи резервного копирования и мониторинга автоматически в облаке не создавались.

Одна ВМ — одна точка отказа. При росте нагрузки можно отдельно внедрить
[Managed PostgreSQL](https://yandex.cloud/ru/docs/managed-postgresql/quickstart)
и [Object Storage](https://yandex.cloud/ru/docs/storage/quickstart).
Текущая поставка использует PostgreSQL в Docker и локальное файловое хранилище,
а не управляемую БД и не S3.
