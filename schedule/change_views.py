from datetime import date

from django import forms
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from main.admin_access import admin_required
from main.notifications import notify_group
from .models import LessonChange, Schedule
from .occurrences import apply_changes
from .timing import campus_now, date_parity, parse_lesson_time


class LessonChangeForm(forms.ModelForm):
    class Meta:
        model = LessonChange
        fields = ['date', 'cancelled', 'subject', 'start', 'end', 'classroom', 'note']
        widgets = {'date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
                   'start': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
                   'end': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M')}

    def __init__(self, *args, lesson, **kwargs):
        self.lesson = lesson
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = 'ds-input'

    def clean(self):
        values = super().clean()
        day, start, end = (values.get(key) for key in ('date', 'start', 'end'))
        if day:
            days = dict(enumerate(name for name, _ in Schedule.DAYS))
            if days.get(day.weekday()) != self.lesson.day or self.lesson.week_parity not in ('all', date_parity(day)):
                self.add_error('date', 'На эту дату у выбранной пары нет занятия. Выберите дату с подходящим днём и чётностью.')
        if start and end and end <= start:
            self.add_error('end', 'Окончание должно быть позже начала.')
        if self.errors or values.get('cancelled'):
            return values
        teachers = {str(value).strip() for value in
                    (self.lesson.first_teacher_id, self.lesson.second_teacher_id) if value and str(value).strip()}
        room = values['classroom'].strip().casefold()
        candidates = Schedule.objects.filter(day=self.lesson.day).exclude(pk=self.lesson.pk).filter(
            Q(week_parity='all') | Q(week_parity=date_parity(day))).select_related('subject', 'group')
        for other in apply_changes(list(candidates), day):
            if other.cancelled:
                continue
            a, b = parse_lesson_time(other.time), parse_lesson_time(other.time_end)
            if not a or not b or not (start < b and a < end):
                continue
            other_teachers = {str(value).strip() for value in
                              (other.first_teacher_id, other.second_teacher_id) if value}
            other_rooms = {str(value).strip().casefold() for value in
                           (other.classroom, other.another_classroom) if value}
            reason = None
            if self.lesson.group_id == other.group_id:
                reason = 'У группы уже есть занятие'
            elif teachers & other_teachers:
                reason = 'Преподаватель занят'
            elif room not in ('', '—', '-', 'онлайн', 'online') and room in other_rooms:
                reason = 'Аудитория занята'
            if reason:
                raise forms.ValidationError(f'{reason}: {other.subject.name}, группа {other.group.number}, {other.time}–{other.time_end}.')
        return values


@admin_required
@require_http_methods(['GET', 'POST'])
def edit_change(request, schedule_id):
    lesson = get_object_or_404(Schedule.objects.select_related('subject', 'group'), pk=schedule_id)
    raw = (request.POST if request.method == 'POST' else request.GET).get('date', '')
    try:
        selected = date.fromisoformat(raw)
    except ValueError:
        selected = campus_now().date()
    with transaction.atomic():
        # Serialize exception edits for this weekday, including different groups.
        if request.method == 'POST':
            list(Schedule.objects.select_for_update().filter(day=lesson.day).order_by('pk').values_list('pk', flat=True))
            lesson.refresh_from_db()
        existing = LessonChange.objects.filter(schedule=lesson, date=selected).first()
        form = LessonChangeForm(request.POST if request.method == 'POST' else None,
            lesson=lesson, instance=existing or LessonChange(schedule=lesson), initial={
                'date': selected, 'subject': lesson.subject_id,
                'start': parse_lesson_time(lesson.time), 'end': parse_lesson_time(lesson.time_end),
                'classroom': lesson.classroom,
            } if not existing else None)
        if request.method == 'POST':
            target = reverse('schedule') + '?date=' + selected.isoformat()
            if request.POST.get('action') == 'restore' and existing and raw == selected.isoformat():
                restore_form = LessonChangeForm({
                    'date': raw, 'subject': lesson.subject_id, 'start': lesson.time,
                    'end': lesson.time_end, 'classroom': lesson.classroom,
                }, lesson=lesson, instance=existing)
                if restore_form.is_valid():
                    existing.delete()
                    notify_group(lesson, 'Занятие восстановлено',
                        f'{selected:%d.%m.%Y} · {lesson.subject.name}. Возвращено обычное расписание.', target)
                    messages.success(request, 'Для этой даты восстановлено обычное расписание.')
                    return redirect(reverse('lesson_change', args=[lesson.pk]) + '?date=' + selected.isoformat())
                form = restore_form
            elif form.is_valid():
                if not existing or form.has_changed():
                    change = form.save(commit=False)
                    change.updated_by = request.user
                    change.save()
                    title = 'Занятие отменено' if change.cancelled else 'Изменение расписания'
                    notify_group(lesson, title,
                        f'{selected:%d.%m.%Y} · {change.subject.name} · {change.start:%H:%M}–{change.end:%H:%M} · {change.classroom}. {change.note}', target)
                messages.success(request, 'Изменение сохранено только для выбранной даты.')
                return redirect(reverse('lesson_change', args=[lesson.pk]) + '?date=' + selected.isoformat())
    return render(request, 'lesson_change.html', {'form': form, 'lesson': lesson,
        'existing': existing, 'selected_date': selected, 'admin_section': 'schedule',
        'changes': lesson.date_changes.select_related('subject')[:20]})
