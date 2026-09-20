from django.db import models
from main.models import Group, CustomUser
from datetime import date


class Subject(models.Model):
    name = models.CharField(max_length=100, verbose_name='Название предмета')

    def __str__(self):
        return self.name


class Homework(models.Model):
    """Отдельная модель для домашних заданий, привязанных к датам"""
    schedule = models.ForeignKey('Schedule', on_delete=models.CASCADE, related_name='homework_assignments')
    content = models.TextField(verbose_name='Текст задания')
    file = models.FileField(upload_to='homework/%Y/%m/%d/', blank=True, null=True, verbose_name='Файл задания')
    assigned_date = models.DateField(default=date.today, verbose_name='Дата задания')
    due_date = models.DateField(blank=True, null=True, verbose_name='Срок сдачи')
    created_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE, verbose_name='Кем задано')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Время создания')
    group = models.ForeignKey(Group, null=True, on_delete=models.CASCADE, verbose_name='Группа')
    subject = models.ForeignKey(Subject, null=True, on_delete=models.CASCADE, verbose_name='Предмет')

    class Meta:
        ordering = ['-assigned_date']
        verbose_name = 'Домашнее задание'
        verbose_name_plural = 'Домашние задания'

    def __str__(self):
        return f"ДЗ для {self.schedule} от {self.assigned_date}"


class Schedule(models.Model):
    DAYS = [
    ('Понедельник', 'Понедельник'),
    ('Вторник', 'Вторник'),
    ('Среда', 'Среда'),
    ('Четверг', 'Четверг'),
    ('Пятница', 'Пятница'),
    ('Суббота', 'Суббота'),
]

    faculty = models.CharField(max_length=100, null=True, verbose_name='Факультет')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, verbose_name='Группа')
    day = models.CharField(max_length=15, choices=DAYS, verbose_name='День недели')
    lesson_number = models.IntegerField(verbose_name='Номер пары')
    first_teacher_id = models.CharField(
        max_length=50,
        null=True,
        unique=False,
        verbose_name='ID Преподавателя'
    )
    first_teacher_name = models.CharField(
        max_length=50,
        null=True,
        unique=False,
        verbose_name='Имя Первого Преподавателя'
    )
    second_teacher_id = models.CharField(
        max_length=50,
        null=True,
        unique=False,
        verbose_name='ID Преподавателя'
    )
    second_teacher_name = models.CharField(
        max_length=50,
        null=True,
        unique=False,
        verbose_name='Имя Второго Преподавателя'
    )
    time = models.CharField(max_length=20, verbose_name='Время')
    time_end = models.CharField(max_length=20, null=True, verbose_name='Время окончания')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, verbose_name='Предмет')
    classroom = models.CharField(max_length=50, verbose_name='Аудитория')
    another_classroom = models.CharField(max_length=50, null=True, verbose_name='Прочие Аудитория')

    # поле для указания чётности недели (декорация, какая пара идёт)
    PARITY_CHOICES = [
        ('all', 'Все недели'),
        ('odd', 'Нечётные недели'),
        ('even', 'Чётные недели'),
    ]
    week_parity = models.CharField(
        max_length=4,
        choices=PARITY_CHOICES,
        default='all',
        verbose_name='Чётность недели',
        help_text='Относительно начала семестра'
    )

    class Meta:
        ordering = ['day', 'lesson_number']
        verbose_name = 'Расписание'
        verbose_name_plural = 'Расписание'

    def __str__(self):
        return f"{self.group} - {self.get_day_display()} - {self.lesson_number} пара"

    def get_homework_for_date(self, target_date):
        """Получить ДЗ для конкретной даты"""
        return self.homework_assignments.filter(assigned_date=target_date).first()