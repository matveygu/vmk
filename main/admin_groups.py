from django.contrib import messages
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from schedule.models import Homework, Schedule

from .admin_access import admin_required
from .admin_group_forms import AdminGroupForm
from .models import CustomUser, Group


@admin_required
@require_http_methods(['GET'])
def admin_groups(request):
    query = request.GET.get('q', '').strip()[:100]
    groups = Group.objects.annotate(
        member_count=Count('customuser', distinct=True),
        lesson_count=Count('schedule', distinct=True),
    ).order_by('faculty', 'course', 'number', 'pk')
    if query:
        groups = groups.filter(Q(number__icontains=query) | Q(faculty__icontains=query))
    page = Paginator(groups, 25).get_page(request.GET.get('page'))
    return render(request, 'admin_groups.html', {
        'admin_section': 'groups',
        'query': query,
        'page_obj': page,
        'groups': page.object_list,
        'group_count': Group.objects.count(),
    })


def _edit_group(request, group=None):
    form = AdminGroupForm(instance=group)
    if request.method == 'POST':
        try:
            with transaction.atomic():
                if group is not None:
                    group = get_object_or_404(Group.objects.select_for_update(), pk=group.pk)
                old_identity = (group.faculty, group.course) if group is not None else None
                form = AdminGroupForm(request.POST, instance=group)
                if form.is_valid():
                    saved = form.save()
                    if old_identity is not None and old_identity != (saved.faculty, saved.course):
                        CustomUser.objects.filter(group=saved).update(faculty=saved.faculty, course=saved.course)
                        Schedule.objects.filter(group=saved).update(faculty=saved.faculty)
                    messages.success(request, f'Группа {saved.number} сохранена.' if group is not None else f'Группа {saved.number} добавлена.')
                    return redirect('admin_groups')
        except IntegrityError:
            form.add_error(None, 'Не удалось сохранить группу: такой номер уже занят на этом факультете. Проверьте данные.')
    return render(request, 'admin_group_form.html', {
        'admin_section': 'groups', 'form': form, 'group': group,
    })


@admin_required
@require_http_methods(['GET', 'POST'])
def admin_group_add(request):
    return _edit_group(request)


@admin_required
@require_http_methods(['GET', 'POST'])
def admin_group_edit(request, group_id):
    return _edit_group(request, get_object_or_404(Group, pk=group_id))


def _related_counts(group):
    return {
        'members': CustomUser.objects.filter(group=group).count(),
        'lessons': Schedule.objects.filter(group=group).count(),
        'homework': Homework.objects.filter(Q(group=group) | Q(schedule__group=group)).count(),
    }


@admin_required
@require_http_methods(['GET', 'POST'])
def admin_group_delete(request, group_id):
    deletion_error = ''
    if request.method == 'POST':
        with transaction.atomic():
            group = get_object_or_404(Group.objects.select_for_update(), pk=group_id)
            related = _related_counts(group)
            if not any(related.values()):
                number = group.number
                group.delete()
                messages.success(request, f'Пустая группа {number} удалена.')
                return redirect('admin_groups')
            deletion_error = 'Группа не удалена: с ней связаны пользователи, занятия или домашние задания.'
    else:
        group = get_object_or_404(Group, pk=group_id)
        related = _related_counts(group)
    return render(request, 'admin_group_confirm.html', {
        'admin_section': 'groups', 'group': group, 'related': related,
        'can_delete': not any(related.values()), 'deletion_error': deletion_error,
    })
