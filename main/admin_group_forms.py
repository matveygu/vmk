from django import forms
from django.core.exceptions import NON_FIELD_ERRORS

from .models import Group


class AdminGroupForm(forms.ModelForm):
    number = forms.IntegerField(
        label='Номер группы',
        min_value=1,
        max_value=2147483647,
        help_text='Курс определяется автоматически по первой цифре номера.',
        widget=forms.NumberInput(attrs={'class': 'ds-input', 'placeholder': 'Например, 105'}),
    )

    class Meta:
        model = Group
        fields = ('number', 'faculty')
        widgets = {
            'faculty': forms.TextInput(attrs={'class': 'ds-input', 'placeholder': 'Например, ВМК'}),
        }
        error_messages = {
            NON_FIELD_ERRORS: {
                'unique_together': 'Группа с таким номером уже существует на этом факультете.',
            },
        }

    def clean_faculty(self):
        faculty = self.cleaned_data['faculty'].strip()
        if not faculty:
            raise forms.ValidationError('Укажите факультет.')
        return faculty
