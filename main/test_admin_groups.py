from unittest.mock import patch

from django.db import IntegrityError
from django.test import Client, TestCase
from django.urls import reverse

from schedule.models import Homework, Schedule, Subject

from .admin_group_forms import AdminGroupForm
from .models import CustomUser, Group


class AdminGroupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = CustomUser.objects.create(username='group-admin', student_id='group-admin', role='admin')
        cls.student = CustomUser.objects.create(username='group-student', student_id='group-student', role='student')
        cls.group = Group.objects.create(number=105, faculty='ВМК')
        cls.subject = Subject.objects.create(name='Математический анализ')

    def setUp(self):
        self.client.force_login(self.admin)

    def urls(self):
        return [
            reverse('admin_groups'), reverse('admin_group_add'),
            reverse('admin_group_edit', args=[self.group.pk]),
            reverse('admin_group_delete', args=[self.group.pk]),
        ]

    def lesson(self, group=None, number=1):
        return Schedule.objects.create(
            group=group or self.group, faculty=(group or self.group).faculty,
            day='Понедельник', lesson_number=number, time='09:00', time_end='10:35',
            subject=self.subject, classroom='101', week_parity='odd',
        )

    def test_administrator_without_django_staff_access_can_open_pages(self):
        self.assertFalse(self.admin.is_staff)
        for url in self.urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_anonymous_and_non_admin_access_is_denied(self):
        self.client.logout()
        for url in self.urls():
            with self.subTest(anonymous=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse('login'), response['Location'])
        for role in ('student', 'teacher', 'headman', 'media', 'uploader'):
            self.student.role = role
            self.student.is_staff = True
            self.student.save(update_fields=['role', 'is_staff'])
            self.client.force_login(self.student)
            for url in self.urls():
                with self.subTest(role=role, url=url):
                    self.assertEqual(self.client.get(url).status_code, 403)
                    self.assertEqual(self.client.post(url, {'number': 999, 'faculty': 'X'}).status_code, 403)
        self.assertEqual(Group.objects.count(), 1)

    def test_create_group_derives_course_and_trims_faculty(self):
        response = self.client.post(reverse('admin_group_add'), {'number': 208, 'faculty': ' ВМК '})
        self.assertRedirects(response, reverse('admin_groups'))
        group = Group.objects.get(number=208)
        self.assertEqual((group.faculty, group.course), ('ВМК', 2))

    def test_invalid_number_and_faculty_have_inline_errors(self):
        for data, field in [
            ({'number': '', 'faculty': 'ВМК'}, 'number'),
            ({'number': '0', 'faculty': 'ВМК'}, 'number'),
            ({'number': '-1', 'faculty': 'ВМК'}, 'number'),
            ({'number': '2147483648', 'faculty': 'ВМК'}, 'number'),
            ({'number': 'abc', 'faculty': 'ВМК'}, 'number'),
            ({'number': '202', 'faculty': '   '}, 'faculty'),
        ]:
            with self.subTest(data=data):
                response = self.client.post(reverse('admin_group_add'), data)
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context['form'].errors)
        self.assertEqual(Group.objects.count(), 1)

    def test_full_positive_integer_range_is_supported(self):
        form = AdminGroupForm(data={'number': 2147483647, 'faculty': 'ВМК'})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().course, 2)

    def test_duplicate_number_in_same_faculty_is_rejected(self):
        response = self.client.post(reverse('admin_group_add'), {'number': 105, 'faculty': 'ВМК'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].non_field_errors())
        self.assertEqual(Group.objects.count(), 1)
        response = self.client.post(reverse('admin_group_add'), {'number': 105, 'faculty': 'Мехмат'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Group.objects.count(), 2)

    def test_edit_updates_group_and_related_identity_only(self):
        self.student.group = self.group
        self.student.faculty = self.group.faculty
        self.student.course = self.group.course
        self.student.name = 'Тестовый участник'
        self.student.phone = '+70000000000'
        self.student.save()
        lesson = self.lesson()
        unrelated = Group.objects.create(number=203, faculty='Физфак')
        other_lesson = self.lesson(group=unrelated)
        response = self.client.post(reverse('admin_group_edit', args=[self.group.pk]), {'number': 305, 'faculty': 'Новый факультет'})
        self.assertRedirects(response, reverse('admin_groups'))
        self.group.refresh_from_db()
        self.student.refresh_from_db()
        lesson.refresh_from_db()
        other_lesson.refresh_from_db()
        self.assertEqual((self.group.number, self.group.faculty, self.group.course), (305, 'Новый факультет', 3))
        self.assertEqual((self.student.faculty, self.student.course, self.student.group_id), ('Новый факультет', 3, self.group.pk))
        self.assertEqual((self.student.name, self.student.phone, self.student.role), ('Тестовый участник', '+70000000000', 'student'))
        self.assertEqual((lesson.faculty, lesson.classroom, lesson.week_parity), ('Новый факультет', '101', 'odd'))
        self.assertEqual(other_lesson.faculty, 'Физфак')

    def test_unchanged_identity_does_not_overwrite_other_user_fields(self):
        self.student.group = self.group
        self.student.faculty = 'Отдельное значение'
        self.student.course = 8
        self.student.save()
        response = self.client.post(reverse('admin_group_edit', args=[self.group.pk]), {'number': 106, 'faculty': 'ВМК'})
        self.assertEqual(response.status_code, 302)
        self.student.refresh_from_db()
        self.assertEqual((self.student.faculty, self.student.course), ('Отдельное значение', 8))

    def test_related_update_failure_rolls_back_group_and_members(self):
        self.student.group = self.group
        self.student.faculty = self.group.faculty
        self.student.course = self.group.course
        self.student.save()
        with patch('main.admin_groups.Schedule.objects.filter') as related_lessons:
            related_lessons.return_value.update.side_effect = IntegrityError('Simulated update failure')
            response = self.client.post(reverse('admin_group_edit', args=[self.group.pk]), {'number': 305, 'faculty': 'Мехмат'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].non_field_errors())
        self.group.refresh_from_db()
        self.student.refresh_from_db()
        self.assertEqual((self.group.number, self.group.faculty, self.group.course), (105, 'ВМК', 1))
        self.assertEqual((self.student.faculty, self.student.course), ('ВМК', 1))

    def test_edit_cannot_duplicate_another_group(self):
        Group.objects.create(number=205, faculty='ВМК')
        response = self.client.post(reverse('admin_group_edit', args=[self.group.pk]), {'number': 205, 'faculty': 'ВМК'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        self.group.refresh_from_db()
        self.assertEqual(self.group.number, 105)

    def test_search_and_distinct_related_counts(self):
        self.student.group = self.group
        self.student.save(update_fields=['group'])
        CustomUser.objects.create(username='group-member-2', student_id='group-member-2', group=self.group)
        self.lesson(number=1)
        self.lesson(number=2)
        Group.objects.create(number=302, faculty='Мехмат')
        response = self.client.get(reverse('admin_groups'), {'q': '105'})
        result = list(response.context['groups'])
        self.assertEqual(len(result), 1)
        self.assertEqual((result[0].member_count, result[0].lesson_count), (2, 2))
        response = self.client.get(reverse('admin_groups'), {'q': 'Мехмат'})
        self.assertEqual(list(response.context['groups'])[0].number, 302)

    def test_get_confirmation_does_not_delete_and_post_deletes_empty_group(self):
        url = reverse('admin_group_delete', args=[self.group.pk])
        response = self.client.get(url)
        self.assertTrue(response.context['can_delete'])
        self.assertTrue(Group.objects.filter(pk=self.group.pk).exists())
        self.assertRedirects(self.client.post(url), reverse('admin_groups'))
        self.assertFalse(Group.objects.filter(pk=self.group.pk).exists())

    def test_group_with_member_cannot_be_deleted(self):
        self.student.group = self.group
        self.student.save(update_fields=['group'])
        response = self.client.post(reverse('admin_group_delete', args=[self.group.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['can_delete'])
        self.assertTrue(response.context['deletion_error'])
        self.assertTrue(Group.objects.filter(pk=self.group.pk).exists())

    def test_group_with_schedule_cannot_be_deleted(self):
        lesson = self.lesson()
        response = self.client.post(reverse('admin_group_delete', args=[self.group.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['can_delete'])
        self.assertTrue(Schedule.objects.filter(pk=lesson.pk).exists())
        self.assertTrue(Group.objects.filter(pk=self.group.pk).exists())

    def test_group_with_direct_homework_relation_cannot_be_deleted(self):
        other_group = Group.objects.create(number=205, faculty='ВМК')
        lesson = self.lesson(group=other_group)
        homework = Homework.objects.create(schedule=lesson, group=self.group, created_by=self.admin, content='Задание')
        response = self.client.post(reverse('admin_group_delete', args=[self.group.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['can_delete'])
        self.assertEqual(response.context['related']['homework'], 1)
        self.assertTrue(Homework.objects.filter(pk=homework.pk).exists())

    def test_mutations_require_csrf_and_supported_methods(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        for url in self.urls()[1:]:
            with self.subTest(url=url):
                self.assertEqual(client.post(url, {'number': 201, 'faculty': 'ВМК'}).status_code, 403)
                self.assertEqual(self.client.put(url, data='{}', content_type='application/json').status_code, 405)
        self.assertEqual(Group.objects.count(), 1)

    def test_missing_group_returns_404(self):
        for name in ('admin_group_edit', 'admin_group_delete'):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name, args=[99999])).status_code, 404)
