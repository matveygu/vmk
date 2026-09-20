"""Integration checks; all fixtures live in Django's isolated test database."""
from urllib.parse import parse_qs, urlparse

from django.test import Client, TestCase
from django.urls import reverse

from main.models import CustomUser, Group
from schedule.models import Homework, Schedule, Subject


class AdminScheduleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = CustomUser.objects.create_user(username='schedule-admin', student_id='admin-schedule', role='admin')
        cls.student = CustomUser.objects.create_user(username='schedule-student', student_id='student-schedule', role='student', is_staff=True)
        cls.teacher = CustomUser.objects.create_user(username='schedule-teacher', student_id='teacher-schedule', role='teacher', name='Преподаватель')
        cls.group = Group.objects.create(number=101, faculty='ВМК', course=1)
        cls.other_group = Group.objects.create(number=201, faculty='Другой факультет', course=2)
        cls.subject = Subject.objects.create(name='Математический анализ')
        cls.other_subject = Subject.objects.create(name='Программирование')

    def setUp(self):
        self.client.force_login(self.admin)

    def lesson(self, **changes):
        values = {
            'group': self.group, 'faculty': self.group.faculty, 'day': 'Понедельник',
            'lesson_number': 1, 'time': '09:00', 'time_end': '10:35',
            'subject': self.subject, 'classroom': 'П-13', 'week_parity': 'all',
            'first_teacher_name': 'Внешний преподаватель', 'first_teacher_id': 'external-001',
            'second_teacher_name': 'Второй преподаватель', 'second_teacher_id': 'external-002',
        }
        values.update(changes)
        return Schedule.objects.create(**values)

    def homework(self, lesson, **changes):
        values = {'schedule': lesson, 'content': 'Задачи 1–3', 'created_by': self.admin, 'group': lesson.group, 'subject': lesson.subject}
        values.update(changes)
        return Homework.objects.create(**values)

    def payload(self, **changes):
        values = {
            'group': self.group.pk, 'subject': self.subject.pk, 'day': 'Понедельник',
            'lesson_number': 1, 'time': '09:00', 'time_end': '10:35', 'classroom': 'П-13',
            'another_classroom': '', 'week_parity': 'all',
            'first_teacher_name': 'Внешний преподаватель', 'first_teacher_id': 'external-001',
            'second_teacher_name': 'Второй преподаватель', 'second_teacher_id': 'external-002',
            'return_group': self.group.pk, 'return_day': 'Понедельник', 'return_parity': 'odd',
        }
        values.update(changes)
        return values

    def test_role_is_required_on_every_schedule_and_subject_screen(self):
        lesson = self.lesson()
        urls = [
            reverse('admin_schedule'), reverse('admin_schedule_create'),
            reverse('admin_schedule_edit', args=[lesson.pk]), reverse('admin_schedule_delete', args=[lesson.pk]),
            reverse('admin_subjects'), reverse('admin_subject_create'),
            reverse('admin_subject_edit', args=[self.subject.pk]), reverse('admin_subject_delete', args=[self.subject.pk]),
        ]
        for user in (self.student, self.teacher):
            self.client.force_login(user)
            for url in urls:
                with self.subTest(user=user.role, url=url):
                    self.assertEqual(self.client.get(url).status_code, 403)
                    self.assertEqual(self.client.post(url, self.payload()).status_code, 403)
        self.client.logout()
        for url in urls:
            with self.subTest(anonymous=url):
                self.assertEqual(self.client.get(url).status_code, 302)

    def test_group_day_and_parity_filter_excludes_unrelated_lessons(self):
        shared = self.lesson()
        odd = self.lesson(lesson_number=2, week_parity='odd')
        self.lesson(lesson_number=3, week_parity='even')
        self.lesson(day='Вторник')
        self.lesson(group=self.other_group)
        response = self.client.get(reverse('admin_schedule'), {'group': self.group.pk, 'day': 'Понедельник', 'parity': 'odd'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item.pk for item in response.context['lessons']], [shared.pk, odd.pk])
        self.assertEqual(len(response.context['day_tabs']), 6)

    def test_bad_filter_ids_do_not_crash_or_leak_other_group_schedule(self):
        self.lesson()
        response = self.client.get(reverse('admin_schedule'), {'group': 'not-an-id', 'day': 'Воскресенье', 'parity': 'invalid'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['filter_form'].errors)
        self.assertFalse(response.context['lessons'])

    def test_create_normalizes_times_uses_group_faculty_and_preserves_filter(self):
        response = self.client.post(reverse('admin_schedule_create'), self.payload(group=self.other_group.pk, time='9:00', faculty='forged', next='https://outside.invalid/'))
        self.assertEqual(response.status_code, 302)
        lesson = Schedule.objects.get()
        self.assertEqual(lesson.faculty, self.other_group.faculty)
        self.assertEqual(lesson.time, '09:00')
        self.assertEqual(lesson.first_teacher_id, 'external-001')
        target = urlparse(response['Location'])
        self.assertFalse(target.netloc)
        self.assertEqual(target.path, reverse('admin_schedule'))
        self.assertEqual(parse_qs(target.query), {'group': [str(self.group.pk)], 'day': ['Понедельник'], 'parity': ['odd']})

    def test_invalid_lesson_inputs_do_not_write(self):
        cases = [
            ({'group': 'missing'}, 'group'), ({'subject': 987654321}, 'subject'),
            ({'day': 'Воскресенье'}, 'day'), ({'week_parity': 'bad'}, 'week_parity'),
            ({'lesson_number': 0}, 'lesson_number'), ({'lesson_number': '1.5'}, 'lesson_number'),
            ({'time': '25:00'}, 'time'), ({'time_end': '08:59'}, 'time_end'),
            ({'time_end': '09:00'}, 'time_end'), ({'time_end': ''}, 'time_end'),
            ({'classroom': ' '}, 'classroom'), ({'first_teacher_id': 'x' * 51}, 'first_teacher_id'),
        ]
        for changes, field in cases:
            with self.subTest(changes=changes):
                response = self.client.post(reverse('admin_schedule_create'), self.payload(**changes))
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context['form'].errors)
                self.assertEqual(Schedule.objects.count(), 0)

    def test_create_without_selected_group_returns_to_visible_new_lesson(self):
        response = self.client.post(reverse('admin_schedule_create'), self.payload(
            return_group='', return_day='Понедельник', return_parity='even',
            group=self.other_group.pk, day='Среда', week_parity='odd',
        ))
        self.assertEqual(response.status_code, 302)
        target = parse_qs(urlparse(response['Location']).query)
        self.assertEqual(target, {'group': [str(self.other_group.pk)], 'day': ['Среда'], 'parity': ['odd']})
        listing = self.client.get(response['Location'])
        self.assertEqual([item.pk for item in listing.context['lessons']], [Schedule.objects.get().pk])

    def test_edit_keeps_external_teacher_ids_and_existing_homework(self):
        lesson = self.lesson()
        homework = self.homework(lesson)
        response = self.client.post(reverse('admin_schedule_edit', args=[lesson.pk]), self.payload(classroom='П-14', first_teacher_name='Уточнённое имя'))
        self.assertEqual(response.status_code, 302)
        lesson.refresh_from_db()
        self.assertEqual(lesson.first_teacher_id, 'external-001')
        self.assertEqual(lesson.second_teacher_id, 'external-002')
        self.assertEqual(lesson.classroom, 'П-14')
        self.assertTrue(Homework.objects.filter(pk=homework.pk).exists())

    def test_group_and_subject_changes_with_homework_are_rejected(self):
        lesson = self.lesson()
        homework = self.homework(lesson)
        response = self.client.post(reverse('admin_schedule_edit', args=[lesson.pk]), self.payload(group=self.other_group.pk, subject=self.other_subject.pk))
        self.assertEqual(response.status_code, 200)
        self.assertIn('group', response.context['form'].errors)
        self.assertIn('subject', response.context['form'].errors)
        lesson.refresh_from_db()
        homework.refresh_from_db()
        self.assertEqual(lesson.group_id, self.group.pk)
        self.assertEqual(lesson.subject_id, self.subject.pk)
        self.assertEqual(homework.group_id, self.group.pk)

    def test_delete_get_is_read_only_and_confirmed_post_deletes_linked_homework(self):
        lesson = self.lesson()
        homework = self.homework(lesson)
        url = reverse('admin_schedule_delete', args=[lesson.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['homework_count'], 1)
        self.assertTrue(Schedule.objects.filter(pk=lesson.pk).exists())
        response = self.client.post(url, self.payload(homework_count=1))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Schedule.objects.filter(pk=lesson.pk).exists())
        self.assertFalse(Homework.objects.filter(pk=homework.pk).exists())

    def test_changed_homework_count_requires_new_confirmation(self):
        lesson = self.lesson()
        self.homework(lesson)
        response = self.client.post(reverse('admin_schedule_delete', args=[lesson.pk]), {'homework_count': 0})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.context['homework_count'], 1)
        self.assertTrue(Schedule.objects.filter(pk=lesson.pk).exists())
        self.assertEqual(Homework.objects.count(), 1)

    def test_subject_create_edit_and_unused_delete(self):
        self.assertEqual(self.client.post(reverse('admin_subject_create'), {'name': '   '}).status_code, 200)
        response = self.client.post(reverse('admin_subject_create'), {'name': 'Новый предмет'})
        self.assertEqual(response.status_code, 302)
        subject = Subject.objects.get(name='Новый предмет')
        response = self.client.post(reverse('admin_subject_edit', args=[subject.pk]), {'name': 'Обновлённый предмет'})
        self.assertEqual(response.status_code, 302)
        subject.refresh_from_db()
        self.assertEqual(subject.name, 'Обновлённый предмет')
        url = reverse('admin_subject_delete', args=[subject.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertTrue(Subject.objects.filter(pk=subject.pk).exists())
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertFalse(Subject.objects.filter(pk=subject.pk).exists())

    def test_subject_rename_is_global(self):
        lesson = self.lesson()
        self.homework(lesson)
        response = self.client.post(reverse('admin_subject_edit', args=[self.subject.pk]), {'name': 'Матанализ'})
        self.assertEqual(response.status_code, 302)
        lesson.refresh_from_db()
        self.subject.refresh_from_db()
        self.assertEqual(lesson.subject.name, 'Матанализ')
        self.assertEqual(Homework.objects.get().subject.name, 'Матанализ')

    def test_used_subject_deletion_protected_for_schedule_and_direct_homework(self):
        lesson = self.lesson()
        response = self.client.post(reverse('admin_subject_delete', args=[self.subject.pk]))
        self.assertEqual(response.status_code, 409)
        self.assertTrue(Schedule.objects.filter(pk=lesson.pk).exists())
        homework = self.homework(lesson, subject=self.other_subject)
        response = self.client.post(reverse('admin_subject_delete', args=[self.other_subject.pk]))
        self.assertEqual(response.status_code, 409)
        self.assertTrue(Subject.objects.filter(pk=self.other_subject.pk).exists())
        self.assertTrue(Homework.objects.filter(pk=homework.pk).exists())

    def test_subject_search_and_crud_preserve_schedule_filters(self):
        params = {'return_group': self.group.pk, 'return_day': 'Среда', 'return_parity': 'even', 'q': 'Математ'}
        response = self.client.get(reverse('admin_subjects'), params)
        self.assertEqual([item.pk for item in response.context['subject_page']], [self.subject.pk])
        params.update(name='Новый предмет', subject_q=params.pop('q'))
        response = self.client.post(reverse('admin_subject_create'), params)
        target = parse_qs(urlparse(response['Location']).query)
        self.assertEqual(target['return_group'], [str(self.group.pk)])
        self.assertEqual(target['return_day'], ['Среда'])
        self.assertEqual(target['return_parity'], ['even'])
        self.assertEqual(target['q'], ['Математ'])

    def test_mutations_require_csrf_and_unsupported_methods_fail(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        lesson = self.lesson()
        urls = [reverse('admin_schedule_create'), reverse('admin_schedule_edit', args=[lesson.pk]), reverse('admin_schedule_delete', args=[lesson.pk]), reverse('admin_subject_create'), reverse('admin_subject_edit', args=[self.subject.pk]), reverse('admin_subject_delete', args=[self.subject.pk])]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(client.post(url, self.payload()).status_code, 403)
                self.assertEqual(self.client.put(url, '{}', content_type='application/json').status_code, 405)
        self.assertEqual(self.client.post(reverse('admin_schedule')).status_code, 405)
        self.assertEqual(self.client.post(reverse('admin_subjects')).status_code, 405)

    def test_unknown_objects_return_404(self):
        for name in ('admin_schedule_edit', 'admin_schedule_delete', 'admin_subject_edit', 'admin_subject_delete'):
            with self.subTest(route=name):
                self.assertEqual(self.client.get(reverse(name, args=[987654321])).status_code, 404)
