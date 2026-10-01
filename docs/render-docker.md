# Запуск Docker-образа на Render

Отправьте `docker/render_start.py` в репозиторий вместе с остальными изменениями.
В настройках сервиса Render замените всё содержимое **Docker Command** на:

```text
python /app/docker/render_start.py
```

Без кавычек, `sh -c` и `&&`. Нужна новая сборка из коммита с этим файлом,
а не перезапуск старого образа. Dockerfile уже копирует каталог docker в /app/docker.

Скрипт проверяет конфигурацию PostgreSQL, выполняет migrate и collectstatic,
затем заменяет процесс на Gunicorn. При ошибке подготовки сервер не запускается.
Используется PORT от Render (по умолчанию 8000). Локальный Compose не изменён.

## Environment

- `DATABASE_URL`: настоящая строка подключения к PostgreSQL. Для Render Postgres
  в том же аккаунте и регионе скопируйте Internal Database URL.
- Удалите `DATABASE_ENGINE`: в проекте эта переменная имеет приоритет над URL.
- `DJANGO_SECRET_KEY`: собственный случайный секрет. Если он попал в чат или
  публичный репозиторий, замените его; пользователям может потребоваться войти заново.
- `DJANGO_DEBUG=False`
- `DJANGO_ALLOWED_HOSTS=msu-study-portal.onrender.com`
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://msu-study-portal.onrender.com`
- `PORTAL_PUBLIC_URL=https://msu-study-portal.onrender.com`

В интерфейсе Environment вставляйте значения без внешних кавычек и без обратных
слешей перед двоеточиями и подчёркиваниями. Не коммитьте секреты и URL базы.

Миграции создают таблицы, но не импортируют локальных пользователей и расписание.
Резервное копирование существующей базы нужно организовать отдельно до деплоя.
Загрузки media должны храниться в постоянном хранилище, а не внутри временного
контейнера. Console email backend не отправляет письма пользователям; для писем
подтверждения и восстановления пароля отдельно настройте SMTP.

Документация: https://render.com/docs/docker
