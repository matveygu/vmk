from django import forms
from .models import Homework, Group


class HomeworkForm(forms.ModelForm):
    class Meta:
        model = Homework
        fields = ['content', 'file', 'due_date']  # ⚡ assigned_date не показываем пользователю

        widgets = {
            'content': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Введите текст задания...'}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }
        labels = {
            'content': 'Текст задания',
            'file': 'Файл (необязательно)',
            'due_date': 'Срок сдачи',
        }


class GroupSelectForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['group'].widget.attrs.update({
            'class': 'ds-select',
            'id': 'groupSelect',
            'required': 'required',
        })
        self.fields['day'].widget.attrs.update({
            'class': 'ds-select',
            'id': 'daySelect',
            'required': 'required',
        })

    group = forms.ModelChoiceField(
        queryset=Group.objects.all().order_by('id'),
        label='',
        empty_label='Выберите группу',
        required=False,
        widget=forms.Select(attrs={
            'class': 'ds-select',
            'id': 'groupSelect',
            'onchange': 'this.form.submit()',
        })
    )

    day = forms.ChoiceField(
        choices=[
            ('', 'Выберите день недели'),
            ('Понедельник', 'Понедельник'),
            ('Вторник', 'Вторник'),
            ('Среда', 'Среда'),
            ('Четверг', 'Четверг'),
            ('Пятница', 'Пятница'),
            ('Суббота', 'Суббота'),
            ('Воскресенье', 'Воскресенье'),
        ],
        label='',
        required=False,
        widget=forms.Select(attrs={
            'class': 'ds-select',
            'id': 'daySelect',
        })
    )
