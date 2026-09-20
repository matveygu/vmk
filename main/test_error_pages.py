"""Authenticated-but-unauthorized access should render the 403 page, not bounce to login."""
from django.test import TestCase
from django.urls import reverse

from .models import CustomUser, Group
from schedule.models import Homework, Schedule, Subject


class ForbiddenPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.group = Group.objects.create(number=101, faculty='ВМК', course=1)
        cls.student = CustomUser.objects.create_user(username='student', student_id='s1', name='Студент', role='student', group=cls.group)
        cls.headman = CustomUser.objects.create_user(username='headman', student_id='s2', name='Староста', role='headman', group=cls.group)
        cls.subject = Subject.objects.create(name='Матан')
        cls.lesson = Schedule.objects.create(
            faculty='ВМК', group=cls.group, day='Понедельник', lesson_number=1,
            time='09:00', subject=cls.subject, classroom='101',
        )
        cls.homework = Homework.objects.create(schedule=cls.lesson, content='Задача 1', created_by=cls.headman, group=cls.group, subject=cls.subject)

    def test_wrong_role_gets_403_page_not_a_login_redirect(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('add_news'))
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, '403.html')
        self.assertContains(response, 'Доступ запрещён', status_code=403)

    def test_anonymous_still_redirected_to_login(self):
        response = self.client.get(reverse('add_news'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_homework_actions_require_headman_role_not_just_login(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse('add_homework', args=[self.lesson.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse('delete_homework', args=[self.homework.pk])).status_code, 403)

    def test_anonymous_homework_delete_redirects_instead_of_crashing(self):
        # delete_homework previously had no @login_required, so an anonymous
        # request hit is_headman_or_above(AnonymousUser) and raised AttributeError.
        response = self.client.post(reverse('delete_homework', args=[self.homework.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_headman_can_still_reach_homework_actions(self):
        self.client.force_login(self.headman)
        response = self.client.get(reverse('add_homework', args=[self.lesson.pk]))
        self.assertEqual(response.status_code, 200)
