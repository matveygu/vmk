"""Generate a new local or Docker environment without overwriting existing files."""
import os
import argparse
from pathlib import Path
import secrets


def create_env(root, local=False):
    target = root / ('.env' if local else '.env.docker')
    content = target.with_name(target.name + '.example').read_text(encoding='utf-8')
    content = content.replace('POSTGRES_PASSWORD=GENERATE_ME', 'POSTGRES_PASSWORD=' + secrets.token_hex(32))
    content = content.replace('DJANGO_SECRET_KEY=GENERATE_ME', 'DJANGO_SECRET_KEY=' + secrets.token_hex(48))
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise SystemExit(f'{target.name} already exists; it has NOT been overwritten.')
    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
        stream.write(content)
    print(f'Created {target.name} with random credentials. Do not commit or share it.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local', action='store_true', help='Create .env for local SQLite instead of Docker.')
    args = parser.parse_args()
    create_env(Path(__file__).resolve().parent.parent, local=args.local)


if __name__ == '__main__':
    main()
