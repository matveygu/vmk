from urllib.parse import urlencode

from django.test import Client, TestCase
from django.urls import reverse

from .models import CustomUser, Group


class AdminUsersTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.group = Group.objects.create(number=105, faculty='ВМК')
        cls.other_group = Group.objects.create(number=205, faculty='Мехмат')
        cls.admin = CustomUser.objects.create_user(username='admin', student_id='a01', name='Admin', role='admin')
        cls.student = CustomUser.objects.create_user(username='ivan', student_id='s101', name='Иван Петров', faculty='ВМК', course=1, group=cls.group)
        cls.teacher = CustomUser.objects.create_user(username='petr', student_id='t202', name='Пётр Иванов', faculty='Мехмат', course=2, group=cls.other_group, role='teacher', is_active=False)
        cls.ungrouped = CustomUser.objects.create_user(username='guest', student_id='s303', name='Анна', faculty='ВМК', course=0)

    def setUp(self):
        self.client.force_login(self.admin)

    def filtered_ids(self, params):
        response = self.client.get(reverse('admin_users'), params)
        self.assertEqual(response.status_code, 200)
        return {u.pk for u in response.context['users']}

    def test_hub_has_three_sections_and_no_user_table(self):
        response = self.client.get(reverse('admin_panel'))
        for name in ('admin_users', 'admin_groups', 'admin_schedule'):
            self.assertContains(response, reverse(name))
        self.assertNotContains(response, 'adm-users-table')

    def test_every_column_is_filterable(self):
        for params, expected in [
            ({'name': 'Иван Пе'}, {self.student.pk}),
            ({'student_id': '101'}, {self.student.pk}),
            ({'faculty': 'Мех'}, {self.teacher.pk}),
            ({'course': '1'}, {self.student.pk}),
            ({'group': str(self.group.pk)}, {self.student.pk}),
            ({'role': 'teacher'}, {self.teacher.pk}),
            ({'status': 'inactive'}, {self.teacher.pk}),
            ({'group': 'none'}, {self.admin.pk, self.ungrouped.pk}),
            ({'course': '0', 'faculty': 'ВМК'}, {self.ungrouped.pk}),
        ]:
            with self.subTest(params=params):
                self.assertEqual(self.filtered_ids(params), expected)

    def test_filters_combine_and_remain_bound(self):
        params = {'name': 'Иван', 'student_id': 's', 'faculty': 'ВМК', 'course': '1', 'group': str(self.group.pk), 'role': 'student', 'status': 'active'}
        response = self.client.get(reverse('admin_users'), params)
        self.assertEqual([u.pk for u in response.context['users']], [self.student.pk])
        for key, value in params.items():
            self.assertEqual(response.context['filter_form'][key].value(), value)

    def test_invalid_filters_are_errors_not_500_or_unfiltered_results(self):
        for params in ({'group': '9999999999999'}, {'course': 'abc'}, {'role': 'unknown'}, {'status': 'bad'}):
            with self.subTest(params=params):
                response = self.client.get(reverse('admin_users'), params)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['filter_form'].errors)
                self.assertFalse(response.context['users'])

    def test_pagination_keeps_filters(self):
        CustomUser.objects.bulk_create([CustomUser(username=f'pg{i}', student_id=f'pg{i}', name=f'Person {i}', faculty='ВМК') for i in range(35)])
        response = self.client.get(reverse('admin_users'), {'faculty': 'ВМК', 'page': 2})
        self.assertEqual(response.context['page_obj'].number, 2)
        self.assertEqual(response.context['page_obj'].paginator.count, 37)
        self.assertIn('faculty=', response.context['filter_query'])
        self.assertEqual(len(response.context['users']), 7)

    def test_edit_synchronizes_group_and_preserves_filters(self):
        query = urlencode({'faculty': 'Мехмат', 'page': 2})
        response = self.client.post(reverse('admin_edit_user', args=[self.student.pk]), {'name': 'Новое имя', 'role': 'headman', 'group': self.other_group.pk, 'return_query': query})
        self.assertEqual(response.url, reverse('admin_users') + '?' + query)
        self.student.refresh_from_db()
        self.assertEqual((self.student.name, self.student.role, self.student.group_id, self.student.course, self.student.faculty), ('Новое имя', 'headman', self.other_group.pk, 2, 'Мехмат'))

    def test_invalid_edit_does_not_partially_save(self):
        response = self.client.post(reverse('admin_edit_user', args=[self.student.pk]), {'name': 'Changed', 'role': 'admin', 'group': '123456789'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        self.student.refresh_from_db()
        self.assertEqual(self.student.name, 'Иван Петров')
        self.assertEqual(self.student.role, 'student')

    def test_admin_cannot_demote_or_disable_self(self):
        response = self.client.post(reverse('admin_edit_user', args=[self.admin.pk]), {'name': 'Admin', 'role': 'student', 'group': ''})
        self.assertTrue(response.context['form'].errors.get('role'))
        self.client.post(reverse('admin_toggle_user', args=[self.admin.pk]))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertEqual(self.admin.role, 'admin')

    def test_toggle_requires_post_and_keeps_query(self):
        url = reverse('admin_toggle_user', args=[self.student.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        response = self.client.post(url, {'return_query': 'status=active'})
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_active)
        self.assertEqual(response.url, reverse('admin_users') + '?status=active')

    def test_only_portal_admin_can_read_or_write(self):
        for role in ('student', 'headman', 'teacher', 'media', 'uploader'):
            self.student.role = role
            self.student.is_staff = True
            self.student.save()
            self.client.force_login(self.student)
            for name, args in [('admin_panel', []), ('admin_users', []), ('admin_edit_user', [self.admin.pk]), ('admin_toggle_user', [self.admin.pk])]:
                with self.subTest(role=role, view=name):
                    self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 403)
                    self.assertEqual(self.client.post(reverse(name, args=args)).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('admin_panel')).status_code, 302)

    def test_csrf_is_required_for_mutation(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(reverse('admin_toggle_user', args=[self.student.pk])).status_code, 403)

    def test_return_query_cannot_redirect_offsite(self):
        response = self.client.post(reverse('admin_toggle_user', args=[self.student.pk]), {'return_query': 'https://example.com/?next=//example.com'})
        self.assertEqual(response.url, reverse('admin_users'))
