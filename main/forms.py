from django import forms
from django.contrib.auth.forms import AuthenticationForm
from .models import News
from django.core.exceptions import ValidationError
import os
from django.contrib.auth.forms import UserCreationForm
from .models import CustomUser, Group
import json
from django.conf import settings


ALLOWED_NEWS_EXTENSIONS = {
    '.pdf', '.png', '.jpg', '.jpeg', '.webp', '.gif',
    '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx', '.txt'
}

MAX_NEWS_FILE_BYTES = 10 * 1024 * 1024  # 10 MB


def get_faculties_list():
    """Загружает список факультетов из JSON файла"""
    json_path = os.path.join(settings.BASE_DIR, 'static', 'data', 'faculties.json')
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            faculties = data.get('faculties', [])
            return [(faculty['name'], faculty['name']) for faculty in faculties]
    except Exception:
        # Если файл не найден, возвращаем пустой список
        return []

class NewsForm(forms.ModelForm):
    def clean_file(self):
        f = self.cleaned_data.get('file')
        if not f:
            return f
        ext = os.path.splitext(f.name)[1].lower()
        if ext not in ALLOWED_NEWS_EXTENSIONS:
            raise ValidationError('Недопустимый тип файла для новости')
        if hasattr(f, 'size') and f.size and f.size > MAX_NEWS_FILE_BYTES:
            raise ValidationError('Файл слишком большой (лимит 10 МБ)')
        return f
    class Meta:
        model = News
        fields = ['title', 'content', 'category', 'file']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'ds-input',
                'placeholder': 'Введите заголовок новости',
                'maxlength': 100
            }),
            'content': forms.Textarea(attrs={
                'class': 'ds-textarea',
                'rows': 4,
                'placeholder': 'Введите содержание новости',
                'maxlength': 200
            }),
            'category': forms.Select(attrs={'class': 'ds-select'}),
            'file': forms.ClearableFileInput(attrs={'class': 'ds-input', 'style': 'padding:8px 14px;height:auto;'}),
        }
        labels = {
            'title': 'Заголовок',
            'content': 'Содержание',
            'category': 'Категория',
            'file': 'Файл',
        }


class CustomAuthForm(AuthenticationForm):
    username = forms.CharField(
        label='Номер студенческого',
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Введите номер студенческого'
        })
    )
    password = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Введите пароль'
        })
    )
    
    def clean(self):
        return super().clean()


class EditProfileForm(forms.ModelForm):
    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if email and CustomUser.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError('Этот email уже используется другим аккаунтом.')
        return email

    email = forms.EmailField(
        label='Email',
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'ds-input',
            'placeholder': 'Введите Email'
        })
    )
    name = forms.CharField(
        label='Полное имя',
        widget=forms.TextInput(attrs={
            'class': 'ds-input',
            'placeholder': 'Введите полное имя'
        })
    )
    phone = forms.CharField(
        label='Телефон',
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'ds-input',
            'placeholder': '+7 (XXX) XXX-XX-XX'
        })
    )
    photo = forms.ImageField(
        label='Фото профиля',
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'ds-input',
            'accept': 'image/*',
            'style': 'padding:8px 14px;height:auto;',
        })
    )
    
    class Meta:
        model = CustomUser
        fields = ('name', 'email', 'phone', 'photo')

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(
        label='Email', max_length=254,
        widget=forms.EmailInput(attrs={'class': 'ds-input', 'autocomplete': 'email', 'placeholder': 'you@example.com'}),
        help_text='Пришлём код подтверждения. Этот адрес нужен для восстановления пароля.',
    )

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise ValidationError('Этот email уже используется. Войдите или восстановите пароль.')
        return email

    name = forms.CharField(
        label='Полное имя',
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Введите полное имя'
        })
    )
    student_id = forms.CharField(
        label='Номер студенческого',
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Введите номер студенческого'
        })
    )
    faculty = forms.ChoiceField(
        label='Факультет',
        choices=[],  # Будут заполнены в __init__
        widget=forms.Select(attrs={
            'class': 'form-control form-control-lg'
        })
    )
    group_number = forms.IntegerField(
        label='Номер группы',
        widget=forms.NumberInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Например: 105'
        }),
        help_text='Курс будет определен автоматически по первой цифре номера'
    )
    password1 = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Введите пароль'
        })
    )
    password2 = forms.CharField(
        label='Подтверждение пароля',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Подтвердите пароль'
        })
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Загружаем список факультетов динамически
        faculties = get_faculties_list()
        self.fields['faculty'].choices = [('', '--- Выберите факультет ---')] + faculties
    
    def clean(self):
        cleaned_data = super().clean()
        faculty = cleaned_data.get('faculty')
        group_number = cleaned_data.get('group_number')
        
        # Проверяем существование группы
        if faculty and group_number:
            try:
                group = Group.objects.get(number=group_number, faculty=faculty)
                # Сохраняем группу для use в save()
                self.cleaned_data['group'] = group
            except Group.DoesNotExist:
                # Привязываем ошибку к полю group_number, чтобы отображать
                # её рядом с соответствующим полем на форме.
                self.add_error('group_number',
                    f'Группа {group_number} факультета {faculty} не найдена. Проверьте данные.')
                # Обнуляем найденный атрибут, чтобы последующий код не ломался
                self.cleaned_data.pop('group', None)
        
        return cleaned_data
    
    class Meta:
        model = CustomUser
        fields = ('name', 'email', 'student_id', 'faculty', 'group_number', 'password1', 'password2')
