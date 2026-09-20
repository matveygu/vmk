"""Consistent PostgreSQL + media backup (Python 3, Windows or Linux host).

Stops only this project's web container during the backup. Keeps PostgreSQL up.
Never deletes older backups. Copy the resulting directory off the VM yourself.
"""
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import tarfile
import uuid


def main():
    root = Path(__file__).resolve().parent.parent
    compose = ['docker', 'compose', '--env-file', str(root / '.env.docker'), '-f', str(root / 'compose.yaml')]

    def run(*args, **kwargs):
        return subprocess.run([*compose, *args], cwd=root, check=True, **kwargs)

    running = run('ps', '--status', 'running', '--services', capture_output=True, text=True).stdout.splitlines()
    if 'db' not in running:
        raise SystemExit('PostgreSQL is not running. Nothing changed.')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    target = root / 'data' / 'backups' / stamp
    target.mkdir(parents=True, mode=0o700)
    web_running = 'web' in running
    try:
        if web_running:
            run('stop', 'web')
        dump = target / 'postgres.dump'
        with os.fdopen(os.open(dump, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
            run('exec', '-T', 'db', 'sh', '-c', 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc', stdout=stream)
        with dump.open('rb') as stream:
            run('exec', '-T', 'db', 'pg_restore', '--list', stdin=stream, stdout=subprocess.DEVNULL)
        media = root / 'data' / 'media'
        archive = target / 'media.tar.gz'
        with tarfile.open(archive, 'w:gz') as bundle:
            if media.is_dir():
                bundle.add(media, arcname='media')
        archive.chmod(0o600)
        (target / 'COMPLETE').touch(mode=0o600)
        print(f'Backup complete: {target}\nCopy it to separate storage. Save .env.docker separately and securely.')
    finally:
        if web_running:
            run('start', 'web')


if __name__ == '__main__':
    main()
