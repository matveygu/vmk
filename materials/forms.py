from django import forms
from .models import Material, MaterialFolder
from django.core.exceptions import ValidationError
import os

ALLOWED_MATERIAL_EXTENSIONS = {
    # Видео
    '.mp4', '.webm', '.ogg', '.mov', '.avi', '.mkv', '.flv', '.m3u8',
    # Аудио
    '.mp3', '.wav', '.aac', '.flac',
    # Изображения
    '.png', '.jpg', '.jpeg', '.webp', '.gif',
    # Документы
    '.pdf', '.djvu',
    # Офис
    '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx', '.txt',
    # Архивы
    '.zip', '.rar', '.7z',
    # Код и скрипты — принимаются как обычные файлы (только просмотр/скачивание,
    # без выполнения или компиляции на сервере).
    '.asm', '.s', '.c', '.h', '.cpp', '.cc', '.cxx', '.hpp',
    '.py', '.pyw', '.java', '.kt', '.js', '.ts', '.cs', '.go', '.rs',
    '.rb', '.php', '.pl', '.sql', '.sh', '.bat', '.ps1',
    '.html', '.css', '.json', '.xml', '.yaml', '.yml',
    '.m', '.r', '.hs', '.lisp', '.scm',
}

MAX_MATERIAL_FILE_BYTES = 1024 * 1024 * 1024  # 1024 MB (для видео)


class MaterialUploadForm(forms.ModelForm):
    new_folder = forms.CharField(
        required=False,
        label='Или создайте новую папку',
        widget=forms.TextInput(attrs={
            'placeholder': 'Введите название новой папки...',
            'class': 'form-control'
        })
    )

    class Meta:
        model = Material
        # 'type' is inferred from file extension, user should not select it
        fields = ['file', 'folder']  # name taken from filename automatically
        widgets = {
            'folder': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        instance = super().save(commit=False)
        # if name not provided, derive from file
        uploaded = self.cleaned_data.get('file')
        if uploaded and not instance.name:
            instance.name = os.path.splitext(os.path.basename(uploaded.name))[0]
        if commit:
            instance.save()
        return instance

    def clean_file(self):
        f = self.cleaned_data.get('file')
        if not f:
            return f
        ext = os.path.splitext(f.name)[1].lower()
        if ext not in ALLOWED_MATERIAL_EXTENSIONS:
            raise ValidationError('Недопустимый тип файла')
        if hasattr(f, 'size') and f.size and f.size > MAX_MATERIAL_FILE_BYTES:
            raise ValidationError('Файл слишком большой (лимит 1 ГБ)')
        return f

class MaterialFilterForm(forms.Form):
    material_type = forms.ChoiceField(choices=[('', 'Все типы')] + Material.TYPES, required=False)


class MaterialEditForm(forms.ModelForm):
    replace_file = forms.BooleanField(required=False, initial=False, label='Заменить файл')

    class Meta:
        model = Material
        fields = ['name', 'file']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'file': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        # if replace_file not checked, keep old file
        if not self.cleaned_data.get('replace_file'):
            self.fields['file'].required = False
            if 'file' in self.changed_data:
                instance.file = self.instance.file
        if commit:
            instance.save()
        return instance

    def clean_file(self):
        f = self.cleaned_data.get('file')
        # Allow empty if not replacing
        if not f:
            return f
        ext = os.path.splitext(f.name)[1].lower()
        if ext not in ALLOWED_MATERIAL_EXTENSIONS:
            raise ValidationError('Недопустимый тип файла')
        if hasattr(f, 'size') and f.size and f.size > MAX_MATERIAL_FILE_BYTES:
            raise ValidationError('Файл слишком большой (лимит 1 ГБ)')
        return f