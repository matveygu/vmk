import os
from django.shortcuts import render, get_object_or_404, redirect, reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, FileResponse
from django.utils import timezone
from datetime import datetime, timedelta, date
from django.conf import settings
from django.db.models import Q, Exists, OuterRef
from main.admin_access import role_required
from .models import Schedule, Subject, Homework, Group
from .forms import HomeworkForm, GroupSelectForm


def is_headman_or_above(user):
    return user.role in ['headman', 'teacher', 'admin']


def get_day_name_from_weekday(weekday):
    """Convert weekday number to Russian day name"""
    days_map = {
        0: 'Понедельник', 1: 'Вторник', 2: 'Среда',
        3: 'Четверг', 4: 'Пятница', 5: 'Суббота', 6: 'Воскресенье'
    }
    return days_map.get(weekday, 'Понедельник')


WEEK_DAY_NAMES = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
WEEK_DAY_SHORT_NAMES = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб']


@login_required
def schedule_view(request):
    user_group = request.user.group

    if not user_group and request.user.role != "teacher":
        context = {
            'schedule': [],
            'week_dates': [],
            'current_date': date.today(),
            'error': '❌ У вас не назначена группа. Обратитесь к администратору.'
        }
        return render(request, 'schedule.html', context)

    # Получаем дату из параметра или текущую дату
    current_date_str = request.GET.get('date', date.today().isoformat())
    try:
        current_date = datetime.strptime(current_date_str, '%Y-%m-%d').date()
    except ValueError:
        current_date = date.today()

    # Вычисляем даты недели
    start_of_week = current_date - timedelta(days=current_date.weekday())
    week_dates = [start_of_week + timedelta(days=i) for i in range(7)]

    # Даты для навигации: "следующая неделя" -> понедельник следующей недели,
    # "предыдущая неделя" -> воскресенье предыдущей недели
    previous_week = (start_of_week - timedelta(days=2)).isoformat()
    next_week = (start_of_week + timedelta(days=7)).isoformat()

    # вычисляем номер недели относительно даты начала семестра (по умолчанию january1)
    semester_start = getattr(settings, 'SEMESTER_START_DATE', date(current_date.year, 1, 1))
    week_number = ((current_date - semester_start).days // 7) + 1
    current_parity = 'even' if week_number % 2 == 0 else 'odd'
    # ручной оверрайд для отладки/навигации
    parity_override = request.GET.get('parity')
    if parity_override in ['even', 'odd', 'all']:
        current_parity = parity_override

    # Получаем день недели для текущей даты
    current_day = get_day_name_from_weekday(current_date.weekday())
    # Расписание на текущий день с учётом чётности
    visible_lessons = Schedule.objects.select_related('subject', 'group')
    if request.user.role != "teacher":
        visible_lessons = visible_lessons.filter(
            faculty=request.user.faculty,
            group=user_group,
        )
        homework = Homework.objects.filter(due_date=current_date, group=user_group)
    else:
        visible_lessons = visible_lessons.filter(
            first_teacher_id=request.user.student_id,
        )
        homework = Homework.objects.filter(due_date=current_date)

    base_qs = visible_lessons.filter(day=current_day)
    if current_parity != 'all':
        base_qs = base_qs.filter(Q(week_parity='all') | Q(week_parity=current_parity))
    schedule = list(base_qs.order_by('lesson_number'))

    homework_by_schedule = {}
    for dz in homework:
        if dz.content:
            homework_by_schedule[dz.schedule_id] = dz
    for lesson in schedule:
        lesson.day_homework = homework_by_schedule.get(lesson.id)

    view_mode = request.GET.get('view', 'day')
    week_schedule = []
    if view_mode == 'week':
        day_indices = {name: index for index, name in enumerate(WEEK_DAY_NAMES)}
        week_schedule = list(visible_lessons.filter(day__in=WEEK_DAY_NAMES).annotate(
            has_homework=Exists(Homework.objects.filter(schedule_id=OuterRef('pk'))),
        ))
        week_schedule.sort(key=lambda lesson: (day_indices[lesson.day], lesson.lesson_number))
        for lesson in week_schedule:
            lesson.row_date = week_dates[day_indices[lesson.day]]

    context = {
        'schedule': schedule,
        'week_schedule': week_schedule,
        'view_mode': view_mode,
        'week_dates': week_dates,
        'current_date': current_date,
        'current_date_str': current_date.isoformat(),
        'previous_week': previous_week,
        'next_week': next_week,
        'homework': homework,
        'form': HomeworkForm(),
        'current_parity': current_parity,
    }
    return render(request, 'schedule.html', context)


def public_schedule_view(request):
    form = GroupSelectForm(request.GET or None)
    schedule_data = None
    group = None
    current_day = request.GET.get('day') or ''
    current_parity = request.GET.get('parity', 'all')
    if current_parity not in ['all', 'even', 'odd']:
        current_parity = 'all'

    if form.is_valid():
        group = form.cleaned_data.get('group')
        day = form.cleaned_data.get('day')
        if not day:
            day = get_day_name_from_weekday(date.today().weekday())
            if day not in WEEK_DAY_NAMES:
                day = WEEK_DAY_NAMES[0]
        current_day = day

        if group:
            schedule_data = Schedule.objects.filter(group_id=group.id, day=day).select_related('subject')
            if current_parity != 'all':
                schedule_data = schedule_data.filter(Q(week_parity='all') | Q(week_parity=current_parity))
            schedule_data = schedule_data.order_by('lesson_number')

    if not current_day:
        current_day = WEEK_DAY_NAMES[0]

    context = {
        'form': form,
        'group': group,
        'week_days': list(zip(WEEK_DAY_NAMES, WEEK_DAY_SHORT_NAMES)),
        'current_day': current_day,
        'current_parity': current_parity,
        'schedule': schedule_data,
    }
    return render(request, 'public.html', context)

@login_required
def day_schedule(request, day):
    """Старая функция для обратной совместимости - перенаправляет на новую систему с датами"""
    # Маппинг старых названий дней на даты текущей недели
    day_mapping = {
        'Понедельник': 0, 'Вторник': 1, 'Среда': 2,
        'Четверг': 3, 'Пятница': 4, 'Суббота': 5
    }

    if day not in day_mapping:
        return redirect('schedule')

    # Вычисляем дату для запрошенного дня
    today = date.today()
    days_difference = day_mapping[day] - today.weekday()
    target_date = today + timedelta(days=days_difference)

    return redirect(f'/schedule/?date={target_date.isoformat()}')


@role_required(is_headman_or_above)
def add_homework(request, schedule_id):
    # Получаем дату из параметра или текущую дату
    current_date_str = request.GET.get('date', date.today().isoformat())
    try:
        current_date = datetime.strptime(current_date_str, '%Y-%m-%d').date()
    except ValueError:
        current_date = date.today()

    # Вычисляем даты недели
    start_of_week = current_date - timedelta(days=current_date.weekday())
    week_dates = [start_of_week + timedelta(days=i) for i in range(7)]
    """Добавление домашнего задания для конкретной пары"""
    schedule = get_object_or_404(Schedule, id=schedule_id)

    if request.method == 'POST':
        form = HomeworkForm(request.POST, request.FILES)
        if form.is_valid():
            homework = form.save(commit=False)
            homework.schedule = schedule
            homework.created_by = request.user
            homework.assigned_date = date.today()  # ⚡ автоматически ставим дату выдачи
            homework.group = schedule.group
            homework.subject = schedule.subject
            homework.save()
            return redirect('schedule_detail', schedule_id=schedule.id)
    else:
        form = HomeworkForm()

    context = {
        'schedule': schedule,
        'week_dates': week_dates,
        'current_date': current_date,
        'current_date_str': current_date.isoformat(),
        'form': form,
    }
    return render(request, 'add_homework.html', context)

@login_required
def download_homework_file(request, schedule_id):
    schedule_item = get_object_or_404(Schedule, id=schedule_id)
    if schedule_item.homework_file:
        response = FileResponse(schedule_item.homework_file.open(), as_attachment=True)
        response['Content-Disposition'] = f'attachment; filename="{schedule_item.homework_file.name}"'
        return response
    else:
        messages.error(request, "Файл не найден")
        return redirect('schedule')


@login_required
def schedule_json(request, day=None):
    user_group = request.user.group

    if not user_group:
        return JsonResponse({'error': 'Group not assigned'}, status=400)

    if day:
        schedule = Schedule.objects.filter(group=user_group, day=day)
    else:
        schedule = Schedule.objects.filter(group=user_group)

    schedule_data = []
    for item in schedule.order_by('day', 'lesson_number'):
        schedule_data.append({
            'day': item.get_day_display(),
            'lesson_number': item.lesson_number,
            'time': item.time,
            'parity': item.week_parity,
            'subject': item.subject.name,
            'teacher': item.first_teacher_name or '',
            'classroom': item.classroom,
            'homework': item.homework,
            'homework_file': item.homework_file.url if item.homework_file else None,
        })

    return JsonResponse({'schedule': schedule_data})


def schedule_detail(request, schedule_id):
    schedule = get_object_or_404(Schedule.objects.select_related('subject', 'group'), id=schedule_id)
    homeworks = []
    if request.user.is_authenticated:
        homeworks = Homework.objects.filter(schedule=schedule).order_by('-created_at')
    context = {
        'schedule': schedule,
        'homeworks': homeworks,
    }
    return render(request, 'schedule_detail.html', context)


@role_required(is_headman_or_above)
def delete_homework(request, schedule_id):
    schedule = get_object_or_404(Homework, id=schedule_id)
    if os.path.isfile(f"media/{schedule.file}"):
        os.remove(f"media/{schedule.file}")
    schedule.delete()
    messages.success(request, 'Домашка успешно удалена')
    return redirect(f'/schedule/?date={schedule.due_date}')
