from django.test import TestCase
from django.urls import reverse

from .models import CustomUser, Group


class PeopleDirectoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.group = Group.objects.create(number=105, faculty='ВМК')
        cls.other_group = Group.objects.create(number=205, faculty='Мехмат')
        cls.viewer = CustomUser.objects.create_user(username='ivan', student_id='s101', name='Иван Петров', faculty='ВМК', course=1, group=cls.group)
        cls.classmate = CustomUser.objects.create_user(username='olga', student_id='s102', name='Ольга Сидорова', faculty='ВМК', course=1, group=cls.group)
        cls.other_student = CustomUser.objects.create_user(username='petr', student_id='s201', name='Пётр Иванов', faculty='Мехмат', course=2, group=cls.other_group)
        cls.disabled = CustomUser.objects.create_user(username='old', student_id='s999', name='Иванова Мария', faculty='ВМК', course=1, group=cls.group, is_active=False)
        cls.groupless_admin = CustomUser.objects.create_user(username='admin', student_id='a01', name='Admin', role='admin')

    def test_anonymous_is_redirected(self):
        response = self.client.get(reverse('people'))
        self.assertEqual(response.status_code, 302)

    def test_first_visit_defaults_to_own_group(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse('people'))
        self.assertEqual(response.status_code, 200)
        ids = {u.pk for u in response.context['people']}
        self.assertEqual(ids, {self.viewer.pk, self.classmate.pk})
        self.assertFalse(response.context['prompt_empty'])

    def test_first_visit_without_own_group_prompts_instead_of_listing_everyone(self):
        self.client.force_login(self.groupless_admin)
        response = self.client.get(reverse('people'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['prompt_empty'])
        self.assertEqual(len(response.context['people']), 0)

    def test_search_by_name_ignores_group_boundaries(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse('people'), {'q': 'Иванов'})
        ids = {u.pk for u in response.context['people']}
        self.assertEqual(ids, {self.other_student.pk})

    def test_search_by_student_id(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse('people'), {'q': 's201'})
        ids = {u.pk for u in response.context['people']}
        self.assertEqual(ids, {self.other_student.pk})

    def test_browsing_another_group_shows_its_roster(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse('people'), {'group': self.other_group.pk})
        ids = {u.pk for u in response.context['people']}
        self.assertEqual(ids, {self.other_student.pk})

    def test_group_and_query_combine(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse('people'), {'group': self.group.pk, 'q': 'Ольга'})
        ids = {u.pk for u in response.context['people']}
        self.assertEqual(ids, {self.classmate.pk})

    def test_disabled_accounts_never_appear(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse('people'), {'q': 'Иванова'})
        self.assertEqual(list(response.context['people']), [])

    def test_explicit_all_groups_with_no_query_prompts(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse('people'), {'group': ''})
        self.assertTrue(response.context['prompt_empty'])

    def test_bad_group_id_is_a_form_error_not_a_crash(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse('people'), {'group': 'not-an-id'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['filter_form'].errors)
