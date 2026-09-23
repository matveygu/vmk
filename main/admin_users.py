from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST
import os
from django.db import connection

from schedule.models import Schedule
from .admin_access import admin_required
from .admin_user_forms import AdminUserEditForm, UserFilterForm
from .models import CustomUser, Group


def _return_query(request):
    raw = request.POST.get('return_query', '') if request.method == 'POST' else request.GET.get('return_query', '')
    # Only known filter keys, never a caller-supplied redirect URL.
    supplied = QueryDict(raw[:4096])
    result = QueryDict(mutable=True)
    for key in [*UserFilterForm.base_fields, 'page']:
        if supplied.get(key):
            result[key] = supplied[key]
    return result.urlencode()


def _users_url(query=''):
    return reverse('admin_users') + ('?' + query if query else '')


@admin_required
@require_GET
def admin_panel(request):
    return render(request, 'admin_panel.html', {
        'build_version': os.environ.get('PORTAL_BUILD_VERSION', 'Локальная разработка'),
        'database_vendor': connection.vendor,
        'stats': {
        'users': CustomUser.objects.count(),
        'groups': Group.objects.count(),
        'schedule': Schedule.objects.count(),
    }})


@admin_required
@require_GET
def admin_users(request):
    data = request.GET.copy()
    if data.get('role') == 'all':
        data['role'] = ''
    form = UserFilterForm(data)
    users = CustomUser.objects.select_related('group').order_by('name', 'pk')
    if form.is_valid():
        filters = form.cleaned_data
        for key in ('name', 'student_id', 'faculty'):
            if filters[key]:
                users = users.filter(**{key + '__icontains': filters[key]})
        if filters['q']:
            users = users.filter(Q(name__icontains=filters['q']) | Q(student_id__icontains=filters['q']))
        if filters['course'] is not None:
            users = users.filter(course=filters['course'])
        if filters['group'] == 'none':
            users = users.filter(group__isnull=True)
        elif filters['group']:
            users = users.filter(group_id=filters['group'])
        if filters['role']:
            users = users.filter(role=filters['role'])
        if filters['status']:
            users = users.filter(is_active=filters['status'] == 'active')
    else:
        users = users.none()
    paginator = Paginator(users, 30)
    page = paginator.get_page(request.GET.get('page'))
    query = data.copy()
    query.pop('page', None)
    return_query = query.copy()
    if page.number > 1:
        return_query['page'] = page.number
    return render(request, 'admin_users.html', {
        'admin_section': 'users', 'filter_form': form, 'page_obj': page,
        'users': page.object_list, 'total_users': CustomUser.objects.count(),
        'filter_query': query.urlencode(), 'return_query': return_query.urlencode(),
        'has_filters': any(value for key, value in query.items()),
    })


@admin_required
@require_http_methods(['GET', 'POST'])
def admin_edit_user(request, user_id):
    target = get_object_or_404(CustomUser, pk=user_id)
    query = _return_query(request)
    form = AdminUserEditForm(request.POST if request.method == 'POST' else None, instance=target, actor=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Пользователь «{target.name}» обновлён.')
        return redirect(_users_url(query))
    return render(request, 'admin_user_form.html', {
        'admin_section': 'users', 'form': form, 'target_user': target,
        'return_query': query, 'back_url': _users_url(query),
    })


@admin_required
@require_POST
def admin_toggle_user(request, user_id):
    target = get_object_or_404(CustomUser, pk=user_id)
    if target.pk == request.user.pk:
        messages.error(request, 'Нельзя отключить собственную учётную запись.')
    else:
        target.is_active = not target.is_active
        target.save(update_fields=['is_active'])
        messages.success(request, f'Пользователь «{target.name}» {"активирован" if target.is_active else "отключён"}.')
    return redirect(_users_url(_return_query(request)))
