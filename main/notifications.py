from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import CustomUser, Notification


def notify(users, title, body, url):
    # No mail or third-party service. Persist alongside the originating transaction.
    recipients = users.filter(is_active=True).values_list('pk', flat=True).distinct()
    Notification.objects.bulk_create([
        Notification(recipient_id=pk, title=title[:200], body=body, url=url)
        for pk in recipients
    ], batch_size=500)


def notify_group(lesson, title, body, url):
    notify(CustomUser.objects.filter(
        Q(group_id=lesson.group_id) |
        Q(role='teacher', student_id__in=[lesson.first_teacher_id, lesson.second_teacher_id])
    ), title, body, url)


@login_required
def inbox(request):
    items = Notification.objects.filter(recipient=request.user)
    unread = items.filter(read_at__isnull=True).count()
    only_unread = request.GET.get('filter') == 'unread'
    if only_unread:
        items = items.filter(read_at__isnull=True)
    return render(request, 'notifications.html', {
        'page_obj': Paginator(items, 30).get_page(request.GET.get('page')),
        'unread_count': unread, 'only_unread': only_unread,
    })


@login_required
@require_POST
def mark_read(request, pk):
    item = get_object_or_404(Notification, pk=pk, recipient=request.user)
    Notification.objects.filter(pk=item.pk, read_at__isnull=True).update(read_at=timezone.now())
    return redirect('notifications')


@login_required
@require_POST
def mark_all_read(request):
    Notification.objects.filter(recipient=request.user, read_at__isnull=True).update(read_at=timezone.now())
    return redirect('notifications')
