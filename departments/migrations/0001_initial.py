from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Department',
            fields=[
                ('id', models.SlugField(max_length=20, primary_key=True, serialize=False, verbose_name='Код')),
                ('abbr', models.CharField(max_length=20, verbose_name='Аббревиатура')),
                ('stream', models.CharField(choices=[('Первый поток', 'Первый поток'), ('Второй поток', 'Второй поток'), ('Третий поток', 'Третий поток'), ('Вне потоков', 'Вне потоков')], max_length=20, verbose_name='Поток')),
                ('name', models.CharField(max_length=255, verbose_name='Название')),
                ('url', models.URLField(verbose_name='Страница на cs.msu.ru')),
                ('head', models.CharField(max_length=255, verbose_name='Заведующий')),
                ('head_note', models.CharField(blank=True, max_length=255, verbose_name='Комментарий о заведующем')),
                ('founded', models.CharField(blank=True, max_length=100, verbose_name='Год основания')),
                ('about', models.TextField(verbose_name='О кафедре')),
                ('directions', models.JSONField(default=list, verbose_name='Научные направления')),
                ('people', models.JSONField(default=list, verbose_name='Преподаватели')),
                ('extra_title', models.CharField(blank=True, max_length=255, verbose_name='Заголовок доп. блока')),
                ('extra_items', models.JSONField(default=list, verbose_name='Пункты доп. блока')),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('phone', models.CharField(blank=True, max_length=50, verbose_name='Телефон')),
                ('site', models.CharField(blank=True, max_length=255, verbose_name='Сайт (отображаемый)')),
                ('site_url', models.URLField(blank=True, verbose_name='Сайт (ссылка)')),
                ('room', models.CharField(blank=True, max_length=255, verbose_name='Комнаты')),
                ('apply_url', models.URLField(blank=True, verbose_name='Материалы о распределении')),
                ('apply_note', models.CharField(blank=True, max_length=500, verbose_name='Примечание о распределении')),
            ],
            options={
                'verbose_name': 'Кафедра',
                'verbose_name_plural': 'Кафедры',
                'ordering': ['stream', 'name'],
            },
        ),
    ]
