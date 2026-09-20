from django import forms

from .models import Group


class PeopleSearchForm(forms.Form):
    group = forms.ModelChoiceField(
        queryset=Group.objects.order_by('faculty', 'course', 'number'), required=False,
        label='Группа', empty_label='Все группы',
        widget=forms.Select(attrs={'class': 'ds-select', 'onchange': 'this.form.submit()'}),
    )
    q = forms.CharField(
        label='Поиск', required=False, max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'ds-input with-icon', 'type': 'search',
            'placeholder': 'Имя, фамилия или студенческий билет',
        }),
    )
