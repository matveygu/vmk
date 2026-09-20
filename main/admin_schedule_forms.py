"""Validated forms for the portal's schedule administration screens."""
from datetime import datetime

from django import forms

from main.models import Group
from schedule.models import Schedule, Subject


class ScheduleFilterForm(forms.Form):
    group = forms.ModelChoiceField(
        queryset=Group.objects.order_by('faculty', 'number'), required=False,
        label='Группа', empty_label='Выберите группу',
        widget=forms.Select(attrs={'class': 'ds-select'}),
    )
    day = forms.ChoiceField(choices=Schedule.DAYS, widget=forms.HiddenInput)
    parity = forms.ChoiceField(choices=Schedule.PARITY_CHOICES, widget=forms.HiddenInput)


class AdminScheduleForm(forms.ModelForm):
    lesson_number = forms.IntegerField(
        label='Номер пары', min_value=1, max_value=99,
        widget=forms.NumberInput(attrs={'class': 'ds-input'}),
    )
    time = forms.TimeField(
        label='Начало', input_formats=['%H:%M'],
        widget=forms.TimeInput(format='%H:%M', attrs={'type': 'time', 'class': 'ds-input'}),
    )
    time_end = forms.TimeField(
        label='Окончание', input_formats=['%H:%M'],
        widget=forms.TimeInput(format='%H:%M', attrs={'type': 'time', 'class': 'ds-input'}),
    )
    first_teacher_name = forms.CharField(label='Первый преподаватель', max_length=50, required=False)
    first_teacher_id = forms.CharField(label='ID первого преподавателя', max_length=50, required=False)
    second_teacher_name = forms.CharField(label='Второй преподаватель', max_length=50, required=False)
    second_teacher_id = forms.CharField(label='ID второго преподавателя', max_length=50, required=False)
    another_classroom = forms.CharField(label='Дополнительная аудитория', max_length=50, required=False)

    class Meta:
        model = Schedule
        fields = [
            'group', 'day', 'subject', 'lesson_number', 'time', 'time_end',
            'classroom', 'another_classroom', 'week_parity',
            'first_teacher_name', 'first_teacher_id', 'second_teacher_name', 'second_teacher_id',
        ]
        labels = {'classroom': 'Аудитория', 'week_parity': 'Чётность недели'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['group'].queryset = Group.objects.order_by('faculty', 'number')
        self.fields['subject'].queryset = Subject.objects.order_by('name', 'pk')
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'ds-select' if isinstance(field.widget, forms.Select) else 'ds-input')
        if self.instance.pk and not self.is_bound:
            for name in ('time', 'time_end'):
                raw = getattr(self.instance, name) or ''
                for time_format in ('%H:%M', '%H:%M:%S'):
                    try:
                        self.initial[name] = datetime.strptime(raw, time_format).time()
                        break
                    except ValueError:
                        continue

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get('time'), cleaned.get('time_end')
        if start and end and end <= start:
            self.add_error('time_end', 'Время окончания должно быть позже начала занятия.')
        if self.instance.pk and self.instance.homework_assignments.exists():
            for name in ('group', 'subject'):
                value = cleaned.get(name)
                if value and value.pk != getattr(self.instance, name + '_id'):
                    self.add_error(name, 'У занятия есть домашние задания. Для смены группы или предмета создайте новое занятие.')
        # The legacy model stores time as text; use one consistent, sortable format.
        for name in ('time', 'time_end'):
            if cleaned.get(name):
                cleaned[name] = cleaned[name].strftime('%H:%M')
        return cleaned

    def save(self, commit=True):
        lesson = super().save(commit=False)
        lesson.faculty = self.cleaned_data['group'].faculty
        if commit:
            lesson.save()
            self.save_m2m()
        return lesson


class AdminSubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        # Teachers are entered as free text per lesson, not tied to the subject.
        fields = ['name']
        labels = {'name': 'Название предмета'}
        widgets = {'name': forms.TextInput(attrs={'class': 'ds-input', 'maxlength': 100})}


class SubjectSearchForm(forms.Form):
    q = forms.CharField(
        required=False, max_length=100, label='Поиск предмета',
        widget=forms.TextInput(attrs={'class': 'ds-input', 'placeholder': 'Название предмета', 'type': 'search'}),
    )


class ScheduleDeleteForm(forms.Form):
    homework_count = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
