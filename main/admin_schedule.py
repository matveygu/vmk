"""Schedule and subject CRUD for administrators, without Django-admin coupling."""
from urllib.parse import urlencode

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from main.admin_access import admin_required
from main.admin_schedule_forms import (
    AdminScheduleForm, AdminSubjectForm, ScheduleDeleteForm, ScheduleFilterForm, SubjectSearchForm,
)
from schedule.models import Homework, LessonChange, Schedule, Subject


def _filter_context(request, *, listing=False, lesson=None):
    source = request.POST if request.method == 'POST' else request.GET
    prefix = '' if listing else 'return_'
    weekday = timezone.localdate().weekday()
    default_day = Schedule.DAYS[weekday if weekday < 6 else 0][0]
    values = {
        'group': source.get(prefix + 'group', lesson.group_id if lesson else ''),
        'day': source.get(prefix + 'day') or (lesson.day if lesson else default_day),
        'parity': source.get(prefix + 'parity') or 'all',
    }
    filter_form = ScheduleFilterForm(values)
    filter_form.is_valid()
    group = filter_form.cleaned_data.get('group')
    day = filter_form.cleaned_data.get('day', default_day)
    parity = filter_form.cleaned_data.get('parity', 'all')
    values = {'group': group.pk if group else '', 'day': day, 'parity': parity}
    return_values = {'return_' + key: value for key, value in values.items()}
    return {
        'admin_section': 'schedule', 'filter_form': filter_form,
        'selected_group': group, 'current_day': day, 'current_parity': parity,
        'filter_query': urlencode(values), 'return_query': urlencode(return_values),
        'return_values': return_values, 'back_url': reverse('admin_schedule') + '?' + urlencode(values),
        'day_tabs': [
            {'name': name, 'short': short, 'url': '?' + urlencode({**values, 'day': name})}
            for (name, _), short in zip(Schedule.DAYS, ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'])
        ],
        'parity_tabs': [
            {'value': value, 'name': name, 'url': '?' + urlencode({**values, 'parity': value})}
            for value, name in [('all', 'Все'), ('odd', 'Нечётная'), ('even', 'Чётная')]
        ],
        'subject_q': source.get('subject_q', source.get('q', '')).strip()[:100],
    }


def _subject_back(context):
    return reverse('admin_subjects') + '?' + context['return_query'] + '&' + urlencode({'q': context['subject_q']})


@admin_required
@require_GET
def admin_schedule(request):
    context = _filter_context(request, listing=True)
    lessons = Schedule.objects.none()
    if context['selected_group']:
        lessons = Schedule.objects.filter(group=context['selected_group'], day=context['current_day'])
        if context['current_parity'] != 'all':
            lessons = lessons.filter(week_parity__in=['all', context['current_parity']])
        lessons = lessons.select_related('subject', 'group').annotate(homework_count=Count('homework_assignments')).order_by('lesson_number', 'time', 'pk')
    context['lessons'] = lessons
    return render(request, 'admin_schedule.html', context)


def _edit_lesson(request, lesson=None):
    context = _filter_context(request, lesson=lesson)
    initial = {'group': context['selected_group'], 'day': context['current_day'], 'week_parity': context['current_parity']}
    form = AdminScheduleForm(request.POST if request.method == 'POST' else None, instance=lesson, initial=initial if lesson is None else None)
    if request.method == 'POST' and form.is_valid():
        saved_lesson = form.save()
        if lesson is None and context['selected_group'] is None:
            context['back_url'] = reverse('admin_schedule') + '?' + urlencode({
                'group': saved_lesson.group_id,
                'day': saved_lesson.day,
                'parity': saved_lesson.week_parity,
            })
        messages.success(request, 'Занятие сохранено.' if lesson else 'Занятие добавлено.')
        return redirect(context['back_url'])
    context.update(form=form, lesson=lesson, subjects_available=Subject.objects.exists())
    return render(request, 'admin_schedule_form.html', context)


@admin_required
@require_http_methods(['GET', 'POST'])
def admin_schedule_create(request):
    return _edit_lesson(request)


@admin_required
@require_http_methods(['GET', 'POST'])
def admin_schedule_edit(request, schedule_id):
    # Lock the row during validation so concurrent changes cannot move an attached assignment.
    with transaction.atomic():
        lesson = get_object_or_404(Schedule.objects.select_for_update().select_related('group', 'subject'), pk=schedule_id)
        return _edit_lesson(request, lesson)


@admin_required
@require_http_methods(['GET', 'POST'])
def admin_schedule_delete(request, schedule_id):
    with transaction.atomic():
        lesson = get_object_or_404(Schedule.objects.select_for_update().select_related('group', 'subject'), pk=schedule_id)
        context = _filter_context(request, lesson=lesson)
        count = lesson.homework_assignments.count()
        form = ScheduleDeleteForm(request.POST if request.method == 'POST' else None, initial={'homework_count': count})
        status = 200
        if request.method == 'POST':
            if form.is_valid() and form.cleaned_data['homework_count'] == count:
                lesson.delete()
                messages.success(request, 'Занятие удалено.' + (f' Удалено домашних заданий: {count}.' if count else ''))
                return redirect(context['back_url'])
            status = 409
            form = ScheduleDeleteForm(initial={'homework_count': count})
            context['confirm_error'] = 'Проверьте актуальное число домашних заданий и подтвердите удаление ещё раз.'
        context.update(lesson=lesson, homework_count=count, form=form)
        return render(request, 'admin_schedule_delete.html', context, status=status)


@admin_required
@require_GET
def admin_subjects(request):
    context = _filter_context(request)
    search_form = SubjectSearchForm(request.GET)
    subjects = Subject.objects.annotate(lesson_count=Count('schedule', distinct=True), homework_count=Count('homework', distinct=True)).order_by('name', 'pk')
    if search_form.is_valid() and search_form.cleaned_data['q']:
        subjects = subjects.filter(name__icontains=search_form.cleaned_data['q'])
    context.update(search_form=search_form, subject_page=Paginator(subjects, 25).get_page(request.GET.get('page')))
    context['subject_query'] = context['return_query'] + '&' + urlencode({'q': context['subject_q']})
    context['subject_edit_query'] = context['return_query'] + '&' + urlencode({'subject_q': context['subject_q']})
    return render(request, 'admin_schedule_subjects.html', context)


def _edit_subject(request, subject=None):
    context = _filter_context(request)
    form = AdminSubjectForm(request.POST if request.method == 'POST' else None, instance=subject)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Название предмета обновлено во всём расписании.' if subject else 'Предмет добавлен.')
        return redirect(_subject_back(context))
    context.update(form=form, subject=subject, subject_back_url=_subject_back(context))
    return render(request, 'admin_schedule_subject_form.html', context)


@admin_required
@require_http_methods(['GET', 'POST'])
def admin_subject_create(request):
    return _edit_subject(request)


@admin_required
@require_http_methods(['GET', 'POST'])
def admin_subject_edit(request, subject_id):
    return _edit_subject(request, get_object_or_404(Subject, pk=subject_id))


@admin_required
@require_http_methods(['GET', 'POST'])
def admin_subject_delete(request, subject_id):
    with transaction.atomic():
        subject = get_object_or_404(Subject.objects.select_for_update(), pk=subject_id)
        context = _filter_context(request)
        lesson_count = Schedule.objects.filter(subject=subject).count()
        homework_count = Homework.objects.filter(subject=subject).count()
        change_count = LessonChange.objects.filter(subject=subject).count()
        used = bool(lesson_count or homework_count or change_count)
        if request.method == 'POST' and not used:
            subject.delete()
            messages.success(request, 'Предмет удалён из справочника.')
            return redirect(_subject_back(context))
        context.update(subject=subject, lesson_count=lesson_count, homework_count=homework_count,
                       change_count=change_count, used=used, subject_back_url=_subject_back(context))
        return render(request, 'admin_schedule_subject_delete.html', context, status=409 if request.method == 'POST' and used else 200)
