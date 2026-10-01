import subprocess
import sys
from unittest import TestCase
from unittest.mock import call, patch

from docker import render_start


class RenderStartTests(TestCase):
    def setUp(self):
        self.enterContext(patch.dict('os.environ', {
            'DATABASE_URL': 'postgresql://test:test@database/test',
        }, clear=True))
        self.chdir = self.enterContext(patch.object(render_start.os, 'chdir'))
        self.run = self.enterContext(patch.object(render_start.subprocess, 'run'))
        self.execvp = self.enterContext(patch.object(render_start.os, 'execvp'))

    def test_prepares_database_and_static_before_server(self):
        sequence = []
        self.run.side_effect = lambda args, **kwargs: sequence.append(args[2])
        self.execvp.side_effect = lambda *args: sequence.append('gunicorn')
        render_start.main()
        self.assertEqual(sequence, ['migrate', 'collectstatic', 'gunicorn'])
        self.chdir.assert_called_once_with(render_start.ROOT)
        self.assertEqual(self.run.call_args_list, [
            call([sys.executable, 'manage.py', 'migrate', '--noinput'], check=True),
            call([sys.executable, 'manage.py', 'collectstatic', '--noinput'], check=True),
        ])
        self.assertIn('0.0.0.0:8000', self.execvp.call_args.args[1])

    def test_uses_render_port(self):
        with patch.dict('os.environ', {'PORT': '10000'}):
            render_start.main()
        self.assertIn('0.0.0.0:10000', self.execvp.call_args.args[1])

    def test_migration_failure_stops_startup(self):
        self.run.side_effect = subprocess.CalledProcessError(1, ['manage.py', 'migrate'])
        with self.assertRaises(subprocess.CalledProcessError):
            render_start.main()
        self.assertEqual(self.run.call_count, 1)
        self.execvp.assert_not_called()

    def test_static_failure_stops_startup(self):
        self.run.side_effect = [None, subprocess.CalledProcessError(1, ['manage.py', 'collectstatic'])]
        with self.assertRaises(subprocess.CalledProcessError):
            render_start.main()
        self.execvp.assert_not_called()

    def test_missing_or_wrong_database_url_fails_before_changes(self):
        for value in ('', 'sqlite:///db.sqlite3', 'https://example.org'):
            with self.subTest(value=value), patch.dict('os.environ', {'DATABASE_URL': value}):
                with self.assertRaises(ValueError):
                    render_start.main()
        self.run.assert_not_called()
        self.execvp.assert_not_called()

    def test_engine_override_is_rejected(self):
        for value in ('sqlite', 'postgresql'):
            with self.subTest(value=value), patch.dict('os.environ', {'DATABASE_ENGINE': value}):
                with self.assertRaises(ValueError):
                    render_start.main()
        self.run.assert_not_called()

    def test_invalid_port_fails_before_changes(self):
        for value in ('', '0', '65536', 'abc', '8000; exit', '²'):
            with self.subTest(value=value), patch.dict('os.environ', {'PORT': value}):
                with self.assertRaises(ValueError):
                    render_start.main()
        self.run.assert_not_called()
