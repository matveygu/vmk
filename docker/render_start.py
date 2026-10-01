"""Render Docker Command: python /app/docker/render_start.py.

Run preparation without shell quoting, then replace this process with Gunicorn.
Local Compose keeps its existing command and update workflow.
"""
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent.parent


def main():
    database_url = os.environ.get('DATABASE_URL', '').strip()
    if not database_url or urlsplit(database_url).scheme not in ('postgres', 'postgresql'):
        raise ValueError('Set DATABASE_URL to your PostgreSQL connection URL in Render Environment.')
    if os.environ.get('DATABASE_ENGINE', ''):
        raise ValueError('Remove DATABASE_ENGINE from Render Environment to use DATABASE_URL.')
    port = os.environ.get('PORT', '8000')
    if not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ValueError('PORT must be an integer from 1 to 65535.')

    os.chdir(ROOT)
    for command in ('migrate', 'collectstatic'):
        print(f'Render startup: {command}', flush=True)
        subprocess.run([sys.executable, 'manage.py', command, '--noinput'], check=True)

    print('Render startup: starting Gunicorn', flush=True)
    os.execvp('gunicorn', [
        'gunicorn', 'msu_portal.wsgi:application', '--bind', f'0.0.0.0:{port}',
        '--workers', '2', '--threads', '2', '--timeout', '120',
        '--forwarded-allow-ips', '*',
    ])


if __name__ == '__main__':
    try:
        main()
    except ValueError as error:
        # Never print the connection URL: it contains database credentials.
        print(f'Render startup stopped: {error}', file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as error:
        print('Render startup stopped: preparation failed; Gunicorn was not started.', file=sys.stderr)
        sys.exit(error.returncode or 1)
