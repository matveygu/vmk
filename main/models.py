from django.contrib.auth.models import AbstractUser
from django.db import models
import uuid

class CustomUser(AbstractUser):
    ROLES = [
        ('student', 'Студент'),
        ('headman', 'Староста'),
        ('teacher', 'Преподаватель'),
        ('media', 'Медиа (может публиковать новости)'),
        ('uploader', 'Загрузчик (может добавлять материалы и папки)'),
        ('admin', 'Администратор'),
    ]
    first_name = None
    last_name = None
    student_id = models.CharField(
        max_length=20,
        unique=True,
        verbose_name='Номер студенческого'
    )
    faculty = models.CharField(
        max_length=100,
        verbose_name='Факультет',
        default='Не указан'
    )
    course = models.IntegerField(
        verbose_name='Курс',
        default=0
    )
    role = models.CharField(
        max_length=20,
        choices=ROLES,
        default='student',
        verbose_name='Роль'
    )
    photo = models.ImageField(
        upload_to='profiles/',
        blank=True,
        null=True,
        verbose_name='Фото'
    )
    group = models.ForeignKey(
        'Group',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Группа'
    )
    name = models.CharField(
        max_length=255,
        verbose_name='full name',
        null=True,
    )
    phone = models.CharField(
        max_length=20,
        verbose_name='Телефон',
        blank=True,
        null=True,
    )

    def __str__(self):
        return f"{self.name} ({self.student_id})"

    def get_role_display(self):
        return dict(self.ROLES).get(self.role, self.role)

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'


class PendingSignup(models.Model):
    """No account exists until the browser holding this ID verifies its email."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    student_id = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=255)
    password_hash = models.CharField(max_length=128)
    group = models.ForeignKey('Group', on_delete=models.CASCADE)
    code_hash = models.CharField(max_length=64)
    attempts = models.PositiveSmallIntegerField(default=0)
    sent_at = models.DateTimeField()
    expires_at = models.DateTimeField(db_index=True)


class EmailRateLimit(models.Model):
    # HMAC identifiers keep addresses and IPs out of this bookkeeping table.
    key = models.CharField(max_length=64, primary_key=True)
    count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)


class Group(models.Model):
    number = models.IntegerField(
        verbose_name='Номер группы',
        help_text='Например: 105',
        null=True,
        blank=True
    )
    faculty = models.CharField(
        max_length=100,
        verbose_name='Факультет'
    )
    course = models.IntegerField(
        verbose_name='Курс',
        help_text='Определяется по первой цифре номера группы'
    )

    def save(self, *args, **kwargs):
        # Автоматически определяем курс по первой цифре номера группы
        if self.number:
            self.course = int(str(self.number)[0])
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.number} ({self.faculty}, {self.course} курс)"

    class Meta:
        verbose_name = 'Группа'
        verbose_name_plural = 'Группы'
        ordering = ['faculty', 'course', 'number']
        unique_together = ['number', 'faculty']

class News(models.Model):
    CATEGORIES = [
        ('news', 'Новость'),
        ('announcement', 'Объявление'),
        ('event', 'Событие'),
    ]

    title = models.CharField(max_length=200, verbose_name='Заголовок')
    content = models.TextField(verbose_name='Содержание')
    category = models.CharField(max_length=20, choices=CATEGORIES, default='news', verbose_name='Категория')
    author = models.ForeignKey(CustomUser, on_delete=models.CASCADE, verbose_name='Автор')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')
    is_published = models.BooleanField(default=True, verbose_name='Опубликовано')
    file = models.FileField(upload_to='news/', blank=True, null=True, verbose_name='Файл')

    class Meta:
        verbose_name = 'Новость'
        verbose_name_plural = 'Новости'
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def get_short_content(self):
        """Возвращает укороченное содержание (первые 100 символов)"""
        if len(self.content) > 100:
            return self.content[:100] + '...'
        return self.content
