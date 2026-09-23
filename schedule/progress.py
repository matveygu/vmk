from django.contrib.auth.decorators import login_required
from django.db.models import Exists, OuterRef, Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .models import Homework, HomeworkCompletion


def visible_homework(user):
    items = Homework.objects.all()
    if user.role == 'teacher':
        return items.filter(Q(schedule__first_teacher_id=user.student_id) |
                            Q(schedule__second_teacher_id=user.student_id))
    return items.filter(group_id=user.group_id) if user.group_id else items.none()


def with_progress(items, user):
    return items.annotate(is_completed=Exists(HomeworkCompletion.objects.filter(
        homework_id=OuterRef('pk'), user=user)))


@login_required
@require_POST
def set_progress(request, homework_id):
    item = get_object_or_404(visible_homework(request.user), pk=homework_id)
    state = request.POST.get('completed')
    if state == '1':
        HomeworkCompletion.objects.get_or_create(user=request.user, homework=item)
    elif state == '0':
        HomeworkCompletion.objects.filter(user=request.user, homework=item).delete()
    else:
        return HttpResponseBadRequest('Некорректный статус задания.')
    return redirect('homework_list')
