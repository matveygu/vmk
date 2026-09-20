from io import StringIO
import os
from unittest.mock import patch
from urllib.error import URLError

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from docker.healthcheck import check

from .email_auth import allow_email
from .management.commands.migrate_from_sqlite import require_empty_target
from .models import CustomUser


class HealthProbeTests(SimpleTestCase):
    @patch.dict(os.environ, {'DJANGO_ALLOWED_HOSTS': ' portal.example.org,localhost'})
    @patch('docker.healthcheck.build_opener')
    def test_probe_uses_loopback_and_allowed_host(self, build):
        response = build.return_value.open.return_value.__enter__.return_value
        response.status = 200
        response.read.return_value = b'ok'
        self.assertTrue(check())
        args, kwargs = build.return_value.open.call_args
        self.assertEqual(args[0].full_url, 'http://127.0.0.1:8000/_health/')
        self.assertEqual(args[0].get_header('Host'), 'portal.example.org')
        self.assertEqual(args[0].get_header('X-forwarded-proto'), 'https')
        self.assertEqual(kwargs['timeout'], 5)

    @patch('docker.healthcheck.build_opener')
    def test_probe_rejects_wrong_status_or_content(self, build):
        response = build.return_value.open.return_value.__enter__.return_value
        for status, body in ((503, b'unavailable'), (200, b'<html>login</html>'), (302, b'ok')):
            with self.subTest(status=status):
                response.status = status
                response.read.return_value = body
                self.assertFalse(check())

    @patch('docker.healthcheck.build_opener')
    def test_connection_failure_is_unhealthy(self, build):
        build.return_value.open.side_effect = URLError('test connection failure')
        self.assertFalse(check())


@override_settings(SECURE_SSL_REDIRECT=False)
class DeploymentTests(TestCase):
    def test_health_checks_database_without_session_queries(self):
        with self.assertNumQueries(1):
            response = self.client.get('/_health/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'ok')
        self.assertIn('no-store', response['Cache-Control'])
        self.assertNotIn('sessionid', response.cookies)

    @patch('main.deployment_views.connection.cursor', side_effect=OperationalError('private DB details'))
    def test_health_failure_is_generic(self, cursor):
        response = self.client.get('/_health/')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.content, b'unavailable')
        self.assertIn('no-store', response['Cache-Control'])

    def test_health_is_read_only(self):
        self.assertEqual(self.client.post('/_health/').status_code, 405)
        self.assertEqual(self.client.head('/_health/').status_code, 200)

    @override_settings(SECURE_SSL_REDIRECT=True, ALLOWED_HOSTS=['portal.example.org'])
    def test_health_works_behind_https_proxy(self):
        response = self.client.get('/_health/', HTTP_HOST='portal.example.org', HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(response.status_code, 200)

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
