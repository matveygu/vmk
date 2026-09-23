import json
import os
from django.http import FileResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib.auth import login, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from .admin_access import role_required
from django.contrib.auth.forms import PasswordChangeForm
from django.conf import settings
from urllib.parse import quote
from .forms import CustomAuthForm, CustomUserCreationForm, EditProfileForm
from django.core.paginator import Paginator
from datetime import date
from .models import News, CustomUser, Group
from django.db.models import Q, Prefetch
from django.contrib import messages
from .forms import NewsForm
from schedule.models import Schedule, Homework
from schedule.timing import annotate_timing, campus_now, date_parity, milliseconds
from schedule.occurrences import apply_changes
from schedule.progress import visible_homework, with_progress
from django.db import transaction
from .notifications import notify


def is_teacher_or_above(user):
    return user.role in ['teacher', 'admin']


def _style_password_form(form):
    labels = {
        'old_password': 'Текущий пароль',
        'new_password1': 'Новый пароль',
        'new_password2': 'Повторите пароль',
    }
    for field_name, label in labels.items():
        field = form.fields[field_name]
        field.label = label
        field.widget.attrs.update({'class': 'ds-input'})
    return form


def is_news_poster(user):
    """Users allowed to post news: teachers, admins, headmen and media role."""
    return user.role in ['teacher', 'admin', 'media']


def get_day_name_from_weekday(weekday):
    """Convert weekday number to Russian day name"""
    days_map = {
        0: 'Понедельник', 1: 'Вторник', 2: 'Среда',
        3: 'Четверг', 4: 'Пятница', 5: 'Суббота'
    }
    return days_map.get(weekday, 'Воскресенье') 


def load_faculties_from_json():
    """Загружает данные о факультетах из JSON файла"""
    json_path = os.path.join(settings.BASE_DIR, 'static', 'data', 'faculties.json')

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            faculties = data.get('faculties', [])

            # Добавляем пути к локальным логотипам
            for faculty in faculties:
                # Формируем путь к локальному файлу логотипа
                logo_filename = f"{faculty['name'].lower()}.png"
                logo_path = f"images/faculties/{logo_filename}"

                # Проверяем существует ли файл
                full_logo_path = os.path.join(settings.BASE_DIR, 'static', logo_path)
                if os.path.exists(full_logo_path):
                    faculty['local_logo'] = logo_path
                else:
                    faculty['local_logo'] = None

            return faculties
    except FileNotFoundError:
        return get_default_faculties()
    except Exception as e:
        print(f"Ошибка загрузки JSON: {e}")
        return get_default_faculties()


def get_default_faculties():
    """Возвращает тестовые данные с локальными логотипами"""
    return [
        {
            'id': 1,
            'name': 'ВМК',
            'full_name': 'Факультет вычислительной математики и кибернетики',
            'description': 'Ведущий факультет в области computer science в России. Готовит специалистов в области программирования, искусственного интеллекта, анализа данных и кибербезопасности.',
            'points': 424,
            'max_points': 500,
            'previous_points': 414,
            'website': 'https://cs.msu.ru',
            'contact': 'vmk@cs.msu.ru',
            'phone': '+7 (495) 939-54-01',
            'local_logo': 'data/faculties/1.png'
        }
    ]


def home(request):
    if request.user.is_authenticated:
        # Получаем расписание на сегодня для текущего пользователя
        today_schedule = []
        now = campus_now()
        schedule_date = now.date()
        if hasattr(request.user, 'group') and request.user.group or request.user.role == 'teacher':
            # Получаем расписание на сегодня
            today_day = get_day_name_from_weekday(schedule_date.weekday())

            if request.user.role != 'teacher':
                today_schedule = Schedule.objects.filter(
                    group=request.user.group,
                    day=today_day
                ).order_by('lesson_number')
            else:
                today_schedule = Schedule.objects.filter(
                    first_teacher_id=request.user.student_id,
                    day=today_day
                ).order_by('lesson_number')

            today_schedule = list(today_schedule.filter(
                Q(week_parity='all') | Q(week_parity=date_parity(schedule_date)),
            ).select_related('subject').prefetch_related(
                Prefetch('homework_assignments',
                         queryset=Homework.objects.filter(assigned_date=schedule_date),
                         to_attr='date_homework'),
            ))
            for lesson in today_schedule:
                lesson.today_homework = lesson.date_homework[0] if lesson.date_homework else None
            today_schedule = apply_changes(today_schedule, schedule_date)
            annotate_timing(today_schedule, schedule_date, now)

        published_news = News.objects.filter(is_published=True).select_related('author').order_by('-created_at')

        context = {
            'today_schedule': today_schedule,
            'upcoming_homework': with_progress(visible_homework(request.user), request.user)
                .filter(is_completed=False, due_date__gte=schedule_date)
                .select_related('subject', 'schedule__subject').order_by('due_date', 'pk')[:3],
            'latest_news': published_news[:3],
            'news_total_count': published_news.count(),
            'today': schedule_date,
            'timing_now': milliseconds(now),
        }
        return render(request, 'home.html', context)
    else:
        from departments.models import Department
        programs = [
            ('Бакалавриат', '«Прикладная математика и информатика» и «Фундаментальные информатика и информационные технологии», 4 года'),
            ('Магистратура', 'Углублённая подготовка по направлениям факультета, 2 года'),
            ('Аспирантура', 'Подготовка научно-педагогических кадров'),
            ('Второе высшее', 'Отдельное отделение; условия обучения уточняйте на сайте факультета'),
        ]
        context = {
            'department_count': Department.objects.count(),
            'programs': programs,
        }
        return render(request, 'public_landing.html', context)


def login_view(request):
    if request.method == 'POST':
        form = CustomAuthForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            if user is not None:
                login(request, user)
                return redirect('home')
    else:
        form = CustomAuthForm()
    return render(request, 'login.html', {'form': form})


def register_view(request):
    # Compatibility for code importing the previous view directly.
    from .email_auth import register
    return register(request)


@login_required
def profile(request):
    return render(request, 'profile.html')


@login_required
def edit_profile(request):
    """Редактирование профиля пользователя и смена пароля"""
    if request.method == 'POST' and 'change_password' in request.POST:
        form = EditProfileForm(instance=request.user)
        password_form = _style_password_form(PasswordChangeForm(user=request.user, data=request.POST))
        if password_form.is_valid():
            user = password_form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Пароль успешно обновлён')
            return redirect('edit_profile')
        else:
            for errors in password_form.errors.values():
                for error in errors:
                    messages.error(request, error)
    elif request.method == 'POST':
        form = EditProfileForm(request.POST, request.FILES, instance=request.user)
        password_form = _style_password_form(PasswordChangeForm(user=request.user))
        if form.is_valid():
            # Удаляем старую фотографию если загружена новая
            if 'photo' in request.FILES and request.user.photo:
                try:
                    request.user.photo.storage.delete(request.user.photo.name)
                except Exception:
                    pass

            form.save()
            messages.success(request, 'Профиль успешно обновлен')
            return redirect('profile')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = EditProfileForm(instance=request.user)
        password_form = _style_password_form(PasswordChangeForm(user=request.user))

    return render(request, 'edit_profile.html', {'form': form, 'password_form': password_form})


@login_required
def news_list(request):
    """Отдельная лента новостей с фильтром по категориям"""
    category = request.GET.get('category', 'all')
    news_qs = News.objects.filter(is_published=True).select_related('author').order_by('-created_at')
    if category in dict(News.CATEGORIES):
        news_qs = news_qs.filter(category=category)

    paginator = Paginator(news_qs, 4)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'page_obj': page_obj,
        'category': category,
    }
    return render(request, 'news.html', context)


@login_required
def homework_list(request):
    from django.core.paginator import Paginator
    from schedule.progress import visible_homework, with_progress
    today = campus_now().date()
    items = with_progress(visible_homework(request.user), request.user)
    status = request.GET.get('status', 'todo')
    if status not in ('todo', 'overdue', 'done', 'all'):
        status = 'todo'
    active_count = items.filter(is_completed=False).count()
    if status == 'done':
        items = items.filter(is_completed=True)
    elif status == 'overdue':
        items = items.filter(is_completed=False, due_date__lt=today)
    elif status == 'todo':
        items = items.filter(is_completed=False)
    page = Paginator(items.select_related('schedule__subject', 'subject')
                     .order_by('due_date', '-assigned_date', '-pk'), 30).get_page(request.GET.get('page'))
    context = {'items': page.object_list, 'page_obj': page, 'status': status,
               'active_count': active_count, 'today': today}
    return render(request, 'homework.html', context)


@role_required(is_news_poster)
def add_news(request):
    """Добавление новости"""
    next_url = request.POST.get('next') or request.GET.get('next') or reverse('home')
    if request.method == 'POST':
        form = NewsForm(request.POST, request.FILES)
        if form.is_valid():
            news = form.save(commit=False)
            news.author = request.user
            with transaction.atomic():
                news.save()
                if news.is_published:
                    notify(CustomUser.objects.all(), 'Новая публикация', news.title, reverse('news_list'))
            messages.success(request, 'Новость успешно добавлена')
            return redirect(next_url)
    else:
        form = NewsForm()

    return render(request, 'add_news.html', {'form': form, 'next_url': next_url})


@role_required(is_news_poster)
def edit_news(request, news_id):
    """Редактирование новости"""
    news = get_object_or_404(News, id=news_id)
    file = news.file
    next_url = request.POST.get('next') or request.GET.get('next') or reverse('home')
    if request.method == 'POST':
        form = NewsForm(request.POST, request.FILES, instance=news)
        if form.is_valid():
            # Delete old file from storage if a new file is uploaded
            if 'file' in form.changed_data and file:
                try:
                    file.storage.delete(file.name)
                except Exception:
                    pass
            form.save()
            messages.success(request, 'Новость успешно обновлена')
            return redirect(next_url)
    else:
        form = NewsForm(instance=news)

    return render(request, 'edit_news.html', {'form': form, 'news': news, 'next_url': next_url})


@role_required(is_news_poster)
def delete_news(request, news_id):
    """Удаление новости"""
    news = get_object_or_404(News, id=news_id)
    next_url = request.POST.get('next') or reverse('home')
    if request.method == 'POST':
        # Remove associated file via storage first
        if news.file:
            try:
                news.file.storage.delete(news.file.name)
            except Exception:
                pass
        news.delete()
        messages.success(request, 'Новость успешно удалена')
    return redirect(next_url)

@login_required
def download_news(request, news_id):
    news = get_object_or_404(News, id=news_id)
    if news.file:
        ext = os.path.splitext(news.file.name)[1]
        filename = news.title or os.path.basename(news.file.name)
        if ext and not filename.lower().endswith(ext.lower()):
            filename += ext
        response = FileResponse(news.file.open(), as_attachment=True)
        # RFC 5987 filename* for unicode
        filename_encoded = quote(filename.encode('utf-8'), safe='')
        response['Content-Disposition'] = (
            f"attachment; filename*=UTF-8''{filename_encoded}"
        )
        return response
    else:
        messages.error(request, "Файл не найден")
        return redirect('home')


DPO_PROGRAMS = [
    {'badge': 'Набор открыт', 'title': 'Вечерняя математическая школа', 'audience': 'Школьники 8–10 классов',
     'format': 'Очно · 2-й учебный корпус МГУ', 'duration': 'Октябрь — май, раз в неделю'},
    {'badge': 'Набор открыт', 'title': 'Подготовительные курсы', 'audience': 'Абитуриенты',
     'format': 'Очно и дистанционно', 'duration': 'Учебный год'},
    {'title': 'Компьютерные курсы Учебного центра', 'audience': 'Все категории слушателей',
     'format': 'Очно · вечерние группы', 'duration': 'От 2 месяцев'},
    {'title': 'Повышение квалификации учителей', 'audience': 'Школьные учителя информатики и математики',
     'format': 'Очно-заочно', 'duration': '72–144 часа'},
    {'title': 'Суперкомпьютерные системы и приложения', 'audience': 'Специалисты с высшим образованием',
     'format': 'Очно · с удостоверением МГУ', 'duration': 'Программа повышения квалификации'},
    {'title': 'Второе высшее образование', 'audience': 'Бакалавры, специалисты, магистры',
     'format': 'Вечерняя форма', 'duration': '3 года'},
]


def programs_view(request):
    """Дополнительное образование — публичная страница"""
    return render(request, 'programs.html', {'programs': DPO_PROGRAMS})


ABITURIENT_DATA = {
    'exams': [
        {'name': 'Математика', 'kind': 'ЕГЭ, профильный уровень', 'min': 39, 'icon': 'fas fa-square-root-variable'},
        {'name': 'Информатика и ИКТ', 'kind': 'ЕГЭ, по выбору с физикой', 'min': 44, 'icon': 'fas fa-code'},
        {'name': 'Физика', 'kind': 'ЕГЭ, по выбору с информатикой', 'min': 39, 'icon': 'fas fa-atom'},
        {'name': 'Русский язык', 'kind': 'ЕГЭ', 'min': 40, 'icon': 'fas fa-book'},
        {'name': 'Математика', 'kind': 'ДВИ, письменный экзамен МГУ', 'min': 30, 'icon': 'fas fa-pen-ruler'},
    ],
    'scores': [
        {'year': '2026', 'pmi': 301, 'fiit': 294, 'budget': '340 мест'},
        {'year': '2025', 'pmi': 298, 'fiit': 291, 'budget': '340 мест'},
        {'year': '2024', 'pmi': 295, 'fiit': 288, 'budget': '335 мест'},
        {'year': '2023', 'pmi': 292, 'fiit': 284, 'budget': '330 мест'},
    ],
    'steps': [
        {'title': 'Зарегистрироваться в личном кабинете абитуриента МГУ', 'note': 'Регистрация открывается 20 июня. Потребуется паспорт и СНИЛС.'},
        {'title': 'Подать заявление на «Прикладную математику и информатику» или ФИИТ', 'note': 'До 5 из 10 направлений МГУ, приоритеты выставляются в заявлении.'},
        {'title': 'Загрузить документы и подтверждения индивидуальных достижений', 'note': 'Аттестат, результаты ЕГЭ подгружаются автоматически, олимпиады и ГТО — вручную.'},
        {'title': 'Записаться на ДВИ по математике и сдать его', 'note': 'Экзамен проходит в июле во 2-м учебном корпусе, расписание в личном кабинете.'},
        {'title': 'Подать согласие на зачисление', 'note': 'Согласие подаётся однократно, до окончания приёма оригиналов.'},
    ],
    'dates': [
        {'d': '20 июня', 't': 'Начало приёма документов'},
        {'d': '10 июля', 't': 'Завершение приёма для поступающих с ДВИ'},
        {'d': '12 — 22 июля', 't': 'Дополнительные вступительные испытания'},
        {'d': '9 августа', 't': 'Публикация конкурсных списков'},
        {'d': '12 августа', 't': 'Приказ о зачислении'},
    ],
}


def abiturient_view(request):
    """Информация для поступающих — публичная страница"""
    return render(request, 'abiturient.html', ABITURIENT_DATA)
