"""Generate isolated Docker credentials without reading/changing the existing .env."""
import os
from pathlib import Path
import secrets


def main():
    root = Path(__file__).resolve().parent.parent
    target = root / '.env.docker'
    content = (root / '.env.docker.example').read_text(encoding='utf-8')
    content = content.replace('POSTGRES_PASSWORD=GENERATE_ME', 'POSTGRES_PASSWORD=' + secrets.token_hex(32))
    content = content.replace('DJANGO_SECRET_KEY=GENERATE_ME', 'DJANGO_SECRET_KEY=' + secrets.token_hex(48))
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise SystemExit('.env.docker already exists; it has NOT been overwritten.')
    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
        stream.write(content)
    print('Created .env.docker with random credentials. Do not commit or share it.')


if __name__ == '__main__':
    main()
