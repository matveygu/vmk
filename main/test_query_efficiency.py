"""Regression checks: adding rows must not add one SQL query per row."""
from datetime import date, datetime
from unittest.mock import patch

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from main.models import CustomUser, Group, News
from materials.models import Material, MaterialFolder
from schedule.models import Homework, Schedule, Subject


@override_settings(SECURE_SSL_REDIRECT=False, SEMESTER_START_DATE=date(2026, 1, 1))
class QueryEfficiencyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.group = Group.objects.create(number=105, faculty='ВМК')
        cls.user = CustomUser.objects.create_user(username='query-test', student_id='query-test',
                                                 group=cls.group, faculty='ВМК', role='student')
        cls.subject = Subject.objects.create(name='Тестовый предмет')

    def setUp(self):
        self.client.force_login(self.user)

    def lesson(self, number, **extra):
        return Schedule.objects.create(group=self.group, faculty='ВМК', subject=self.subject,
                                       day='Понедельник', lesson_number=number, time='09:00',
                                       classroom='101', first_teacher_id=self.user.student_id, **extra)

    def measure(self, url, params=None):
        # Warm template/session caches before comparing the same page.
        self.client.get(url, params or {})
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(url, params or {})
        self.assertEqual(response.status_code, 200)
        return len(queries), response

    def compare_lessons(self, label, url, params):
        lesson = self.lesson(1)
        Homework.objects.create(schedule=lesson, subject=self.subject, group=self.group,
                                created_by=self.user, assigned_date=date(2026, 1, 5),
                                due_date=date(2026, 1, 5), content='Первое задание')
        before, _ = self.measure(url, params)
        for number in range(2, 22):
            self.lesson(number)
        after, response = self.measure(url, params)
        print(f'Query profile {label}, 1 -> 21 lessons: {before} -> {after}')
        self.assertEqual(before, after, label)
        return response

    def test_day_schedule_queries_do_not_grow(self):
        response = self.compare_lessons('day', reverse('schedule'), {'date': '2026-01-05'})
        self.assertEqual(len(response.context['schedule']), 21)
        self.assertContains(response, 'Первое задание')

    def test_week_schedule_queries_do_not_grow(self):
        response = self.compare_lessons('week', reverse('schedule'), {'date': '2026-01-05', 'view': 'week'})
        lessons = response.context['week_schedule']
        self.assertEqual(len(lessons), 21)
        self.assertTrue(lessons[0].has_homework)
        self.assertFalse(lessons[-1].has_homework)
        self.assertEqual(lessons[0].row_date, date(2026, 1, 5))

    def test_public_schedule_queries_do_not_grow(self):
        response = self.compare_lessons('public', reverse('public_schedule'),
                                        {'group': self.group.pk, 'day': 'Понедельник'})
        self.assertEqual(len(response.context['schedule']), 21)

    def test_teacher_week_queries_and_visibility(self):
        self.user.role = 'teacher'
        self.user.save(update_fields=['role'])
        other_group = Group.objects.create(number=205, faculty='ВМК')
        Schedule.objects.create(group=other_group, subject=self.subject, day='Понедельник',
                                lesson_number=99, time='09:00', classroom='102',
                                first_teacher_id='someone-else')
        response = self.compare_lessons('teacher week', reverse('schedule'),
                                        {'date': '2026-01-05', 'view': 'week'})
        self.assertEqual(len(response.context['week_schedule']), 21)
        self.assertTrue(all(lesson.first_teacher_id == self.user.student_id
                            for lesson in response.context['week_schedule']))

    def test_home_queries_do_not_grow(self):
        with patch('main.views.date') as day, patch('main.views.datetime') as clock:
            day.today.return_value = date(2026, 1, 5)
            clock.now.return_value = datetime(2026, 1, 5, 10)
            response = self.compare_lessons('home', reverse('home'), {})
        self.assertEqual(len(response.context['today_schedule']), 21)
        self.assertContains(response, 'Первое задание')

    def test_news_author_queries_do_not_grow(self):
        News.objects.create(title='Новость 0', content='Текст', author=self.user)
        before, _ = self.measure(reverse('news_list'))
        for n in range(1, 4):
            News.objects.create(title=f'Новость {n}', content='Текст', author=self.user)
        after, response = self.measure(reverse('news_list'))
        print(f'Query profile news, 1 -> 4 items: {before} -> {after}')
        self.assertEqual(before, after)
        self.assertEqual(len(response.context['page_obj']), 4)

    @patch('django.core.files.storage.filesystem.FileSystemStorage.size', return_value=10)
    def test_folder_queries_do_not_grow_and_stats_stay_correct(self, size):
        def folder(n):
            root = MaterialFolder.objects.create(name=f'Корень {n:02}', created_by=self.user)
            MaterialFolder.objects.create(name=f'Дочерняя {n}', created_by=self.user, parent_folder=root)
            Material.objects.create(name=f'Файл {n}', file='materials/test.txt', folder=root, uploaded_by=self.user)
        folder(0)
        before, _ = self.measure(reverse('materials_drive_root'))
        for n in range(1, 21):
            folder(n)
        after, response = self.measure(reverse('materials_drive_root'))
        print(f'Query profile drive, 1 -> 21 folders: {before} -> {after}')
        self.assertEqual(before, after)
        self.assertEqual(len(response.context['subfolders']), 21)
        for item in response.context['subfolders']:
            self.assertEqual(item.material_count, 2)
            self.assertEqual(item.material_size, 10)

    def test_repeated_drive_visit_does_not_write_session(self):
        self.client.get(reverse('materials_drive_root'))
        with CaptureQueriesContext(connection) as queries:
            self.client.get(reverse('materials_drive_root'))
        writes = [q['sql'] for q in queries if q['sql'].startswith(('UPDATE', 'INSERT')) and 'django_session' in q['sql']]
        self.assertEqual(len(writes), 0)

    def test_repeated_folder_visit_does_not_write_session(self):
        folder = MaterialFolder.objects.create(name='Текущая', created_by=self.user)
        url = reverse('materials_drive_folder', args=[folder.pk])
        self.client.get(url)
        with CaptureQueriesContext(connection) as queries:
            self.client.get(url)
        writes = [q for q in queries if q['sql'].startswith(('UPDATE', 'INSERT')) and 'django_session' in q['sql']]
        self.assertEqual(len(writes), 0)
        self.assertEqual(self.client.session['selected_folder_id'], folder.pk)
        self.client.get(reverse('materials_drive_root'))
        self.assertIsNone(self.client.session['selected_folder_id'])
