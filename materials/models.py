import os
from django.db import models
from main.models import Group, CustomUser


class MaterialFolder(models.Model):
    name = models.CharField(max_length=200, verbose_name='Название папки')
    parent_folder = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True,
                                      verbose_name='Родительская папка')
    created_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE, verbose_name='Создатель')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')

    class Meta:
        verbose_name = 'Папка материалов'
        verbose_name_plural = 'Папки материалов'
        ordering = ['name']

    def __str__(self):
        path = f"/{self.parent_folder}"
        return f"{path}/{self.name}"


class Material(models.Model):
    # material categories (stored for icon/label purposes)
    # this list is mostly for display; the actual value is inferred from file
    TYPES = [
        ('video', 'Видео'),
        ('audio', 'Аудио'),
        ('image', 'Изображение'),
        ('document', 'Документ'),
        ('text', 'Текст'),
        ('presentation', 'Презентация'),
        ('code', 'Исходный код'),
        ('other', 'Другое'),
    ]

    name = models.CharField(max_length=200, verbose_name='Название')
    file = models.FileField(upload_to='materials/', verbose_name='Файл')
    type = models.CharField(max_length=20, choices=TYPES, verbose_name='Тип материала')
    folder = models.ForeignKey(MaterialFolder, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Папка')
    uploaded_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE, verbose_name='Загрузил')
    upload_date = models.DateTimeField(auto_now_add=True, verbose_name='Дата загрузки')
    subject = models.ForeignKey('schedule.Subject', on_delete=models.SET_NULL,
                                null=True, blank=True, verbose_name='Предмет')
    semester = models.PositiveSmallIntegerField('Семестр', null=True, blank=True,
        choices=[(number, str(number)) for number in range(1, 13)])

    class Meta:
        verbose_name = 'Материал'
        verbose_name_plural = 'Материалы'
        ordering = ['-upload_date']
        constraints = [models.CheckConstraint(condition=models.Q(semester__isnull=True) |
            models.Q(semester__gte=1, semester__lte=12), name='material_semester_range')]

    def __str__(self):
        return self.name

    @classmethod
    def guess_type(cls, filename_or_ext: str) -> str:
        """Return one of the TYPE keys based on a file extension."""
        ext = os.path.splitext(filename_or_ext)[1].lower()
        if ext in ['.mp4', '.webm', '.ogg', '.mov', '.avi', '.mkv', '.flv', '.m3u8']:
            return 'video'
        if ext in ['.mp3', '.wav', '.ogg', '.aac', '.flac']:
            return 'audio'
        if ext in ['.png', '.jpg', '.jpeg', '.webp', '.gif']:
            return 'image'
        if ext in ['.pdf', '.djvu']:
            return 'document'
        if ext in ['.txt', '.md', '.csv', '.log', '.ini']:
            return 'text'
        if ext in ['.ppt', '.pptx', '.key']:
            return 'presentation'
        if ext in [
            '.asm', '.s', '.c', '.h', '.cpp', '.cc', '.cxx', '.hpp',
            '.py', '.pyw', '.java', '.kt', '.js', '.ts', '.cs', '.go', '.rs',
            '.rb', '.php', '.pl', '.sql', '.sh', '.bat', '.ps1',
            '.html', '.css', '.json', '.xml', '.yaml', '.yml',
            '.m', '.r', '.hs', '.lisp', '.scm',
        ]:
            return 'code'
        return 'other'

    def save(self, *args, **kwargs):
        # auto-fill name from filename if not specified
        if self.file and (not self.name or self.name.strip() == ''):
            self.name = os.path.splitext(os.path.basename(self.file.name))[0]
        # determine type by extension so user doesn't choose it
        if self.file:
            self.type = self.guess_type(self.file.name)
        super().save(*args, **kwargs)


class MaterialFavorite(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name='favorites')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'material'], name='unique_material_favorite')]
