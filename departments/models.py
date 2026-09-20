from django.db import models

STREAM_CHOICES = [
    ('Первый поток', 'Первый поток'),
    ('Второй поток', 'Второй поток'),
    ('Третий поток', 'Третий поток'),
    ('Вне потоков', 'Вне потоков'),
]

# Fixed reading order for the public "Кафедры" page — mirrors the order
# distribution happens in (streams I–III), with non-streamed departments last.
STREAM_ORDER = ['Первый поток', 'Второй поток', 'Третий поток', 'Вне потоков']


class Department(models.Model):
    """Кафедра факультета ВМК. Данные — с cs.msu.ru/departments."""

    id = models.SlugField(primary_key=True, max_length=20, verbose_name='Код')
    abbr = models.CharField(max_length=20, verbose_name='Аббревиатура')
    stream = models.CharField(max_length=20, choices=STREAM_CHOICES, verbose_name='Поток')
    name = models.CharField(max_length=255, verbose_name='Название')
    url = models.URLField(verbose_name='Страница на cs.msu.ru')

    head = models.CharField(max_length=255, verbose_name='Заведующий')
    head_note = models.CharField(max_length=255, blank=True, verbose_name='Комментарий о заведующем')
    founded = models.CharField(max_length=100, blank=True, verbose_name='Год основания')
    about = models.TextField(verbose_name='О кафедре')

    directions = models.JSONField(default=list, verbose_name='Научные направления')
    people = models.JSONField(default=list, verbose_name='Преподаватели')

    extra_title = models.CharField(max_length=255, blank=True, verbose_name='Заголовок доп. блока')
    extra_items = models.JSONField(default=list, verbose_name='Пункты доп. блока')

    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True, verbose_name='Телефон')
    site = models.CharField(max_length=255, blank=True, verbose_name='Сайт (отображаемый)')
    site_url = models.URLField(blank=True, verbose_name='Сайт (ссылка)')
    room = models.CharField(max_length=255, blank=True, verbose_name='Комнаты')

    apply_url = models.URLField(blank=True, verbose_name='Материалы о распределении')
    apply_note = models.CharField(max_length=500, blank=True, verbose_name='Примечание о распределении')

    class Meta:
        verbose_name = 'Кафедра'
        verbose_name_plural = 'Кафедры'
        ordering = ['stream', 'name']

    def __str__(self):
        return self.name

    def stream_number(self):
        return {'Первый поток': 'I', 'Второй поток': 'II', 'Третий поток': 'III', 'Вне потоков': '—'}.get(self.stream, '—')
