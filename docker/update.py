"""Update this checkout only: python C:/path/to/vmk/docker/update.py.

Build, backup, migrations, static assets, health and running-version verification.
Never removes volumes. --check performs read-only preflight checks.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent


def run(command, *, capture=False, env=None):
    return subprocess.run(command, cwd=ROOT, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None, env=env)


def validate_checkout(containers):
    for container in containers:
        if container['Config']['Labels'].get('com.docker.compose.service') != 'web':
            continue
        saved = container['Config']['Labels'].get('com.docker.compose.project.working_dir', '')
        if not saved or os.path.normcase(os.path.abspath(saved)) != os.path.normcase(str(ROOT)):
            raise RuntimeError('Existing web container belongs to another checkout: '
                               f'{saved or "unknown"}. Expected: {ROOT}. '
                               'Resolve which data/media directory to use before updating. Nothing stopped.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Read-only configuration and Docker checks')
    args = parser.parse_args()
    print(f'Project directory: {ROOT}', flush=True)
    compose = ['docker', 'compose', '--project-directory', str(ROOT),
               '--env-file', str(ROOT / '.env.docker'), '-f', str(ROOT / 'compose.yaml')]
    run([*compose, 'config', '--quiet'])
    run(['docker', 'info', '--format', '{{.ServerVersion}}'])
    ids = run([*compose, 'ps', '-aq'], capture=True).stdout.split()
    if ids:
        containers = json.loads(run(['docker', 'inspect', *ids], capture=True).stdout)
        validate_checkout(containers)
    if args.check:
        print('Preflight passed. Run without --check to update.')
        return
    revision = run(['git', 'rev-parse', '--short', 'HEAD'], capture=True).stdout.strip()
    dirty = bool(run(['git', 'status', '--porcelain'], capture=True).stdout.strip())
    version = revision + ('-work' if dirty else '') + '-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    print(f'Building version: {version}', flush=True)
    run([*compose, 'build', '--build-arg', f'PORTAL_BUILD_VERSION={version}', 'web'])
    run([*compose, 'up', '-d', '--wait', '--wait-timeout', '120', 'db'])
    # backup.py anchors its own compose paths to exactly the same checkout.
    run([sys.executable, str(ROOT / 'docker' / 'backup.py')])
    run([*compose, 'stop', 'web'])
    try:
        run([*compose, 'run', '--rm', '--no-deps', 'web', 'python', 'manage.py', 'migrate', '--noinput'])
        run([*compose, 'run', '--rm', '--no-deps', 'web', 'python', 'manage.py', 'collectstatic', '--noinput'])
        run([*compose, 'up', '-d', '--no-deps', '--force-recreate', '--wait', '--wait-timeout', '120', 'web'])
        actual = run([*compose, 'exec', '-T', 'web', 'printenv', 'PORTAL_BUILD_VERSION'], capture=True).stdout.strip()
        if actual != version:
            raise RuntimeError('Running version differs from the built version.')
    except (subprocess.CalledProcessError, RuntimeError):
        print('Update incomplete. Backup is in data/backups. Check container status; '
              'the previous application is not automatically restarted after schema changes.', file=sys.stderr)
        raise
    print(f'Update verified: {version}. Open http://127.0.0.1:8000/ and check the admin overview.')


if __name__ == '__main__':
    try:
        main()
    except (subprocess.CalledProcessError, RuntimeError, FileNotFoundError) as error:
        print(f'Update stopped: {error}', file=sys.stderr)
        sys.exit(1)
