from datetime import date, datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings
from django.urls import reverse

from main.models import CustomUser, Group, Notification
from .change_views import LessonChangeForm
from .models import Homework, HomeworkCompletion, LessonChange, Schedule, Subject
from .occurrences import apply_changes
from .timing import annotate_timing


@override_settings(SECURE_SSL_REDIRECT=False, SEMESTER_START_DATE=date(2026, 9, 1))
class StudyWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.group = Group.objects.create(number=101, faculty='ВМК')
        cls.other_group = Group.objects.create(number=102, faculty='ВМК')
        cls.student = CustomUser.objects.create_user(username='student-work', student_id='student-work',
            group=cls.group, faculty='ВМК', role='student')
        cls.peer = CustomUser.objects.create_user(username='peer-work', student_id='peer-work',
            group=cls.group, faculty='ВМК', role='student')
        cls.outsider = CustomUser.objects.create_user(username='other-work', student_id='other-work',
            group=cls.other_group, faculty='ВМК', role='student')
        cls.admin = CustomUser.objects.create_user(username='admin-work', student_id='admin-work', role='admin')
        cls.subject = Subject.objects.create(name='Алгоритмы')
        cls.lesson = Schedule.objects.create(group=cls.group, faculty='ВМК', subject=cls.subject,
            day='Понедельник', lesson_number=1, time='09:00', time_end='10:30', classroom='101',
            first_teacher_id='teacher-work')
        cls.hw = Homework.objects.create(schedule=cls.lesson, subject=cls.subject, group=cls.group,
            content='Задача на графы', created_by=cls.admin, due_date=date(2026, 9, 21))

    def change_data(self, **kwargs):
        return {'date': '2026-09-21', 'subject': self.subject.pk, 'start': '11:00',
                'end': '12:30', 'classroom': '202', 'note': 'Разовая замена', **kwargs}

    def save_change(self, **kwargs):
        self.client.force_login(self.admin)
        return self.client.post(reverse('lesson_change', args=[self.lesson.pk]), self.change_data(**kwargs))

    def test_completion_is_private_idempotent_and_reversible(self):
        url = reverse('homework_progress', args=[self.hw.pk])
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(url).status_code, 405)
        for _ in range(2):
            self.assertEqual(self.client.post(url, {'completed': '1'}).status_code, 302)
        self.assertEqual(HomeworkCompletion.objects.count(), 1)
        self.assertContains(self.client.get(reverse('homework_list'), {'status': 'done'}), self.hw.content)
        self.assertNotContains(self.client.get(reverse('homework_list')), self.hw.content)
        self.client.force_login(self.peer)
        self.assertContains(self.client.get(reverse('homework_list')), self.hw.content)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.post(url, {'completed': '1'}).status_code, 404)
        self.client.force_login(self.student)
        self.client.post(url, {'completed': '0'})
        self.assertFalse(HomeworkCompletion.objects.exists())

    def test_overdue_excludes_completed_and_undated(self):
        self.client.force_login(self.student)
        Homework.objects.create(schedule=self.lesson, group=self.group, created_by=self.admin,
                                content='Без срока', due_date=None)
        with patch('main.views.campus_now', return_value=datetime(2026, 9, 23, tzinfo=ZoneInfo('Europe/Moscow'))):
            response = self.client.get(reverse('homework_list'), {'status': 'overdue'})
            self.assertContains(response, self.hw.content)
            self.assertNotContains(response, 'Без срока')
            HomeworkCompletion.objects.create(user=self.student, homework=self.hw)
            self.assertNotContains(self.client.get(reverse('homework_list'), {'status': 'overdue'}), self.hw.content)

    def test_date_change_does_not_mutate_recurring_row_or_other_dates(self):
        self.assertEqual(self.save_change().status_code, 302)
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.time, '09:00')
        occurrence = apply_changes([self.lesson], date(2026, 9, 21))[0]
        self.assertEqual(occurrence.time, '11:00')
        self.assertEqual(occurrence.classroom, '202')
        self.assertEqual(apply_changes([self.lesson], date(2026, 9, 28))[0].classroom, '101')
        self.assertEqual(self.lesson.classroom, '101')
        self.client.force_login(self.student)
        for params in ({'date': '2026-09-21'}, {'date': '2026-09-21', 'view': 'week'}):
            response = self.client.get(reverse('schedule'), params)
            self.assertContains(response, 'Разовая замена')
            self.assertContains(response, '11:00')
        self.client.logout()
        self.assertContains(self.client.get(reverse('public_schedule'),
            {'date': '2026-09-21', 'group': self.group.pk}), 'Разовая замена')

    def test_cancellation_is_visible_but_not_current_and_can_be_restored(self):
        self.save_change(cancelled='on')
        row = apply_changes([self.lesson], date(2026, 9, 21))[0]
        annotate_timing([row], date(2026, 9, 21), datetime(2026, 9, 21, 11, 15, tzinfo=ZoneInfo('Europe/Moscow')))
        self.assertTrue(row.cancelled)
        self.assertEqual(row.timing_start, '')
        self.assertEqual(row.timing_state, '')
        self.client.post(reverse('lesson_change', args=[self.lesson.pk]), {'date': '2026-09-21', 'action': 'restore'})
        self.assertFalse(LessonChange.objects.exists())
        self.assertFalse(apply_changes([self.lesson], date(2026, 9, 21))[0].cancelled)

    def test_admin_only_and_invalid_dates_do_not_write(self):
        self.client.force_login(self.student)
        url = reverse('lesson_change', args=[self.lesson.pk])
        self.assertEqual(self.client.post(url, self.change_data()).status_code, 403)
        self.client.force_login(self.admin)
        for value in ('bad', '2026-09-22'):
            self.assertEqual(self.client.post(url, self.change_data(date=value)).status_code, 200)
            self.assertFalse(LessonChange.objects.exists())
        self.client.post(url, self.change_data(end='10:00'))
        self.assertFalse(LessonChange.objects.exists())

    def test_conflicts_include_group_room_and_second_teacher(self):
        for fields in ({'group': self.group, 'classroom': '999'},
                       {'group': self.other_group, 'classroom': '202'},
                       {'group': self.other_group, 'classroom': '999', 'second_teacher_id': 'teacher-work'}):
            other = Schedule.objects.create(subject=self.subject, day='Понедельник',
                lesson_number=2, time='12:00', time_end='13:30', **fields)
            form = LessonChangeForm(self.change_data(), lesson=self.lesson,
                                    instance=LessonChange(schedule=self.lesson))
            self.assertFalse(form.is_valid())
            LessonChange.objects.create(schedule=other, date=date(2026, 9, 21), subject=self.subject,
                start=time(12), end=time(13, 30), classroom=other.classroom, cancelled=True)
            form = LessonChangeForm(self.change_data(), lesson=self.lesson,
                                    instance=LessonChange(schedule=self.lesson))
            self.assertTrue(form.is_valid(), form.errors)
            other.delete()

    def test_notifications_target_group_and_do_not_duplicate_unchanged_save(self):
        self.save_change()
        self.assertEqual(set(Notification.objects.values_list('recipient_id', flat=True)),
                         {self.student.pk, self.peer.pk})
        self.save_change()
        self.assertEqual(Notification.objects.count(), 2)
        item = Notification.objects.get(recipient=self.student)
        self.client.force_login(self.outsider)
        self.assertNotContains(self.client.get(reverse('notifications')), 'Разовая замена')
        self.assertEqual(self.client.post(reverse('notification_read', args=[item.pk])).status_code, 404)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse('notification_read', args=[item.pk])).status_code, 405)
        self.client.post(reverse('notifications_read_all'))
        item.refresh_from_db()
        self.assertIsNotNone(item.read_at)
        self.assertIsNone(Notification.objects.get(recipient=self.peer).read_at)

    def test_homework_create_notifies_only_the_group(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('add_homework', args=[self.lesson.pk]),
            {'content': 'Новое задание', 'due_date': '2026-09-28'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(set(Notification.objects.values_list('recipient_id', flat=True)),
                         {self.student.pk, self.peer.pk})

    def test_restore_rejects_conflict_created_during_cancellation(self):
        self.save_change(cancelled='on')
        Schedule.objects.create(subject=self.subject, group=self.group, day='Понедельник',
            lesson_number=2, time='09:30', time_end='10:00', classroom='999')
        response = self.client.post(reverse('lesson_change', args=[self.lesson.pk]),
            {'date': '2026-09-21', 'action': 'restore'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(LessonChange.objects.get(schedule=self.lesson).cancelled)
        self.assertContains(response, 'У группы уже есть занятие')

    def test_subject_used_only_in_exception_cannot_be_deleted(self):
        substitute = Subject.objects.create(name='Разовый спецкурс')
        self.save_change(subject=substitute.pk)
        response = self.client.post(reverse('admin_subject_delete', args=[substitute.pk]))
        self.assertEqual(response.status_code, 409)
        self.assertTrue(Subject.objects.filter(pk=substitute.pk).exists())

    def test_new_published_news_notifies_but_drafts_do_not(self):
        from main.models import News
        self.client.force_login(self.admin)
        values = {'title': 'Объявление', 'content': 'Текст', 'category': 'news'}
        self.assertEqual(self.client.post(reverse('add_news'), values).status_code, 302)
        news = News.objects.get(title=values['title'])
        count = Notification.objects.count()
        self.assertEqual(count, CustomUser.objects.filter(is_active=True).count())
        self.client.post(reverse('edit_news', args=[news.pk]), values)
        self.assertEqual(Notification.objects.count(), count)
        draft = News.objects.create(title='Черновик', content='Текст', author=self.admin, is_published=False)
        self.client.post(reverse('edit_news', args=[draft.pk]), values)
        self.assertEqual(Notification.objects.count(), count)

    def test_public_sunday_has_no_monday_lessons(self):
        self.client.logout()
        response = self.client.get(reverse('public_schedule'),
            {'group': self.group.pk, 'date': '2026-09-27'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['current_day'], 'Воскресенье')
        self.assertFalse(response.context['schedule'])
