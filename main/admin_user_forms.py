from django import forms

from .models import CustomUser, Group


class UserFilterForm(forms.Form):
    name = forms.CharField(label='Пользователь', required=False, max_length=255)
    student_id = forms.CharField(label='Студенческий', required=False, max_length=20)
    faculty = forms.CharField(label='Факультет', required=False, max_length=100)
    course = forms.IntegerField(label='Курс', required=False, min_value=0, max_value=2147483647)
    group = forms.ChoiceField(label='Группа', required=False)
    role = forms.ChoiceField(label='Роль', required=False, choices=[('', 'Все роли'), *CustomUser.ROLES])
    status = forms.ChoiceField(label='Статус', required=False, choices=[('', 'Все статусы'), ('active', 'Активный'), ('inactive', 'Отключён')])
    q = forms.CharField(label='Общий поиск', required=False, max_length=255)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['group'].choices = [('', 'Все группы'), ('none', 'Без группы'), *[(str(g.pk), str(g)) for g in Group.objects.all()]]
        for name, field in self.fields.items():
            field.widget.attrs.update({'class': 'ds-select' if isinstance(field.widget, forms.Select) else 'ds-input', 'aria-label': field.label})
            if isinstance(field.widget, forms.TextInput):
                field.widget.attrs['placeholder'] = 'Любой' if name != 'q' else 'Имя или студенческий'


class AdminUserEditForm(forms.ModelForm):
    name = forms.CharField(label='ФИО', max_length=255)

    class Meta:
        model = CustomUser
        fields = ['name', 'role', 'group']
        labels = {'role': 'Роль', 'group': 'Группа'}

    def __init__(self, *args, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        self.fields['group'].queryset = Group.objects.all()
        self.fields['group'].empty_label = 'Без группы'
        self.fields['group'].help_text = 'Факультет и курс обновятся по выбранной группе.'
        for field in self.fields.values():
            field.widget.attrs['class'] = 'ds-select' if isinstance(field.widget, forms.Select) else 'ds-input'

    def clean_role(self):
        role = self.cleaned_data['role']
        if self.actor and self.instance.pk == self.actor.pk and role != 'admin':
            raise forms.ValidationError('Нельзя снять права администратора со своей учётной записи.')
        return role

    def save(self, commit=True):
        user = super().save(commit=False)
        if user.group:
            user.course = user.group.course
            user.faculty = user.group.faculty
        if commit:
            user.save()
        return user
