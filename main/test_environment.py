"""Configuration regression tests; only synthetic credentials are used."""
from contextlib import redirect_stdout
from io import StringIO
import os
from pathlib import Path
import runpy
import tempfile
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase
from dotenv import dotenv_values

from docker.init_env import create_env
from docker.refresh_env import reformat, refresh
from msu_portal.env import env_bool, env_csv, env_int


class EnvironmentTests(SimpleTestCase):
    def test_boolean_parsing(self):
        for value in ('True', 'yes', 'ON', '1', ' false ', 'No', '0', 'off'):
            with self.subTest(value=value), patch.dict(os.environ, {'TEST_BOOL': value}):
                self.assertEqual(env_bool('TEST_BOOL'), value.strip().lower() in ('true', 'yes', 'on', '1'))
        with patch.dict(os.environ, {'TEST_BOOL': 'typo'}):
            with self.assertRaisesMessage(ImproperlyConfigured, 'TEST_BOOL must be True or False'):
                env_bool('TEST_BOOL')

    def test_integer_validation_and_csv(self):
        with patch.dict(os.environ, {'TEST_INT': '0', 'TEST_CSV': ' localhost,example.org,,localhost '}):
            self.assertEqual(env_csv('TEST_CSV'), ['localhost', 'example.org'])
            with self.assertRaises(ImproperlyConfigured):
                env_int('TEST_INT', 10)
        for value in ('bad', '65536'):
            with patch.dict(os.environ, {'TEST_INT': value}):
                with self.assertRaises(ImproperlyConfigured):
                    env_int('TEST_INT', 10, maximum=65535)

    def load_settings(self, **env):
        values = {'DJANGO_DEBUG': 'False', 'DJANGO_SECRET_KEY': 'test-only-not-a-real-secret',
                  'DJANGO_ALLOWED_HOSTS': 'portal.example.org', 'DATABASE_ENGINE': 'sqlite'}
        values.update(env)
        with patch.dict(os.environ, values, clear=True), patch('dotenv.load_dotenv') as load:
            result = runpy.run_path(str(settings.BASE_DIR / 'msu_portal' / 'settings.py'),
                                   run_name='msu_portal._settings_test')
            load.assert_called_once_with(settings.BASE_DIR / '.env', override=False)
            return result

    def test_production_defaults_and_log_level(self):
        result = self.load_settings(LOG_LEVEL='warning', SEMESTER_START_DATE='2026-09-01')
        self.assertTrue(result['SECURE_SSL_REDIRECT'])
        self.assertEqual(result['ALLOWED_HOSTS'], ['portal.example.org'])
        self.assertEqual(result['CSRF_TRUSTED_ORIGINS'], [])
        self.assertEqual(result['LOGGING']['root']['level'], 'WARNING')
        self.assertEqual(str(result['SEMESTER_START_DATE']), '2026-09-01')

    def test_invalid_configuration_is_rejected(self):
        for values in ({'DJANGO_SECRET_KEY': ''}, {'DJANGO_SECRET_KEY': 'GENERATE_ME'},
                       {'DJANGO_ALLOWED_HOSTS': ''}, {'DJANGO_ALLOWED_HOSTS': '*'},
                       {'EMAIL_USE_SSL': 'True'}, {'EMAIL_PORT': 'bad'},
                       {'DATABASE_ENGINE': 'postgre'}, {'DATABASE_ENGINE': 'postgresql'},
                       {'LOG_LEVEL': 'typo'}, {'SEMESTER_START_DATE': 'bad'}):
            with self.subTest(keys=list(values)), self.assertRaises(ImproperlyConfigured):
                self.load_settings(**values)

    def test_reformat_preserves_quotes_multiline_and_custom_settings(self):
        current = "DJANGO_SECRET_KEY='a$# b'\nCUSTOM='line one\nline two'\nGOOGLE_SHEET_ID=old\n"
        template = '# Application\nDJANGO_SECRET_KEY=GENERATE_ME\nLOG_LEVEL=INFO\n'
        result = reformat(current, template)
        parsed = dotenv_values(stream=StringIO(result), interpolate=False)
        self.assertEqual(parsed['DJANGO_SECRET_KEY'], 'a$# b')
        self.assertEqual(parsed['CUSTOM'], 'line one\nline two')
        self.assertNotIn('GOOGLE_SHEET_ID', parsed)
        self.assertEqual(result, reformat(result, template))

    def test_reformat_refuses_duplicates_missing_secrets_and_changed_interpolation(self):
        for current, template in (
            ('A=1\nA=2\n', 'A=3\n'),
            ('A=1\n', 'DJANGO_SECRET_KEY=GENERATE_ME\n'),
            ("A=first\nB=${A}\n", 'B=default\nA=default\n'),
        ):
            with self.subTest(current=current), self.assertRaises(ValueError):
                reformat(current, template)

    def test_refresh_backups_original_bytes_and_is_idempotent(self):
        with tempfile.TemporaryDirectory(dir=settings.DATA_DIR) as directory:
            root = Path(directory)
            original = b'A=original\r\n'
            (root / '.env').write_bytes(original)
            (root / '.env.example').write_text('# Config\nA=default\nB=new\n', encoding='utf-8')
            with redirect_stdout(StringIO()):
                self.assertIsNone(refresh(root))
                self.assertEqual((root / '.env').read_bytes(), original)
                backup = refresh(root, apply=True)
                self.assertEqual((backup / '.env').read_bytes(), original)
                self.assertIsNone(refresh(root, apply=True))

    def test_initialization_never_overwrites_either_profile(self):
        with tempfile.TemporaryDirectory(dir=settings.DATA_DIR) as directory:
            root = Path(directory)
            for name in ('.env', '.env.docker'):
                (root / (name + '.example')).write_text('DJANGO_SECRET_KEY=GENERATE_ME\n', encoding='utf-8')
                with redirect_stdout(StringIO()):
                    create_env(root, local=name == '.env')
                content = (root / name).read_bytes()
                self.assertNotIn(b'GENERATE_ME', content)
                with self.assertRaises(SystemExit):
                    create_env(root, local=name == '.env')
                self.assertEqual((root / name).read_bytes(), content)
