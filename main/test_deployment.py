from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory, TestCase, override_settings

from .email_auth import allow_email
from .management.commands.migrate_from_sqlite import require_empty_target
from .models import CustomUser


@override_settings(SECURE_SSL_REDIRECT=False)
class DeploymentTests(TestCase):
    def test_media_rejects_anonymous(self):
        response = self.client.get('/_media_auth/')
        self.assertEqual(response.status_code, 401)
        self.assertIn('no-store', response['Cache-Control'])

    def test_media_allows_active_user(self):
        user = CustomUser.objects.create_user(username='media-check', student_id='media-check')
        self.client.force_login(user)
        self.assertEqual(self.client.get('/_media_auth/').status_code, 204)
        user.is_active = False
        user.save()
        self.assertEqual(self.client.get('/_media_auth/').status_code, 401)

    @override_settings(TRUST_PROXY_CLIENT_IP=False)
    @patch('main.email_auth.take_limit', return_value=True)
    def test_untrusted_header_is_ignored(self, take):
        request = RequestFactory().get('/', REMOTE_ADDR='192.0.2.1', HTTP_X_REAL_IP='198.51.100.3')
        allow_email(request, 'test@example.org')
        self.assertEqual(take.call_args_list[0].args[1], '192.0.2.1')

    @override_settings(TRUST_PROXY_CLIENT_IP=True)
    @patch('main.email_auth.take_limit', return_value=True)
    def test_proxy_ip_and_invalid_fallback(self, take):
        request = RequestFactory().get('/', REMOTE_ADDR='192.0.2.1', HTTP_X_REAL_IP='198.51.100.3')
        allow_email(request, 'test@example.org')
        self.assertEqual(take.call_args_list[0].args[1], '198.51.100.3')
        take.reset_mock()
        request.META['HTTP_X_REAL_IP'] = 'invalid, 198.51.100.3'
        allow_email(request, 'test@example.org')
        self.assertEqual(take.call_args_list[0].args[1], '192.0.2.1')

    def test_import_refuses_existing_user(self):
        CustomUser.objects.create_user(username='keep-me', student_id='keep-me')
        with self.assertRaisesMessage(CommandError, 'Target is not empty'):
            require_empty_target()
        self.assertTrue(CustomUser.objects.filter(username='keep-me').exists())

    def test_import_refuses_modified_seed(self):
        from departments.models import Department
        Department.objects.create(id='custom', name='Keep this department')
        with self.assertRaisesMessage(CommandError, 'edited departments'):
            require_empty_target()

    def test_database_check(self):
        output = StringIO()
        call_command('check_database', stdout=output)
        self.assertIn('Database ready', output.getvalue())
