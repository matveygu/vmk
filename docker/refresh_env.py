"""Reformat existing environment files using templates, without rotating secrets.

Run without arguments for a dry run; --apply creates a private backup first.
Requires python-dotenv (already in requirements.txt).
"""
import argparse
from datetime import datetime, timezone
from io import StringIO
import os
from pathlib import Path
import tempfile

from dotenv import dotenv_values
from dotenv.parser import parse_stream


# These belonged to the retired Google Sheets scheduler / Render configuration.
OBSOLETE = {
    'GOOGLE_SHEET_ID', 'GOOGLE_CREDENTIALS_PATH', 'SCHEDULE_DEFAULT_FACULTY',
    'SCHEDULE_DEFAULT_COURSE', 'SCHEDULER_ENABLED', 'SCHEDULE_IMPORT_DAY_OF_WEEK',
    'SCHEDULE_IMPORT_HOUR', 'SCHEDULE_IMPORT_MINUTE', 'SCHEDULE_IMPORT_TIMEZONE',
    'RENDER_EXTERNAL_HOSTNAME',
}


def bindings(content):
    result = {}
    for binding in parse_stream(StringIO(content)):
        if binding.error:
            raise ValueError('Invalid env syntax; no files changed.')
        if binding.key:
            if binding.key in result:
                raise ValueError(f'Duplicate variable: {binding.key}; resolve it first.')
            result[binding.key] = binding.original.string
    return result


def reformat(current, template):
    existing = bindings(current)
    bindings(template)  # Validate both inputs before doing anything.
    remaining = dict(existing)
    parts = []
    for binding in parse_stream(StringIO(template)):
        if binding.key in remaining:
            parts.append(remaining.pop(binding.key))
        else:
            parts.append(binding.original.string)
    extras = [raw for key, raw in remaining.items() if key not in OBSOLETE]
    if extras:
        parts.append('\n# Additional existing settings (preserved)\n')
        parts.extend(extras)
    result = ''.join(part.rstrip('\r\n') + '\n' for part in parts)
    # Check both literal and interpolated values: ordering must not alter secrets.
    for interpolate in (False, True):
        before = dotenv_values(stream=StringIO(current), interpolate=interpolate)
        after = dotenv_values(stream=StringIO(result), interpolate=interpolate)
        for key in existing.keys() - OBSOLETE:
            if key not in after or after[key] != before[key]:
                raise ValueError(f'Value would change for {key}; refusing rewrite.')
    values = dotenv_values(stream=StringIO(result), interpolate=False)
    if any(value == 'GENERATE_ME' for value in values.values()):
        raise ValueError('Missing credentials; use init_env.py for a new profile.')
    return result


def refresh(root, apply=False):
    changes = []
    for name in ('.env', '.env.docker'):
        target = root / name
        if not target.exists():
            continue
        original = target.read_bytes()
        updated = reformat(original.decode('utf-8-sig'),
                           (root / (name + '.example')).read_text(encoding='utf-8'))
        if original != updated.encode('utf-8'):
            changes.append((target, original, updated))
    if not apply or not changes:
        print(f'{len(changes)} environment file(s) need formatting; secrets not displayed.')
        return None
    backup_parent = root / 'data' / 'backups'
    backup_parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-')
    backup = Path(tempfile.mkdtemp(prefix='env-' + stamp, dir=backup_parent))
    for target, original, _ in changes:
        with os.fdopen(os.open(backup / target.name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), 'wb') as stream:
            stream.write(original)
    for target, _, updated in changes:
        fd, temporary = tempfile.mkstemp(prefix='.env.refresh-', dir=root)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
                stream.write(updated)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    print(f'Updated {len(changes)} file(s), retained values verified. Private backup: {backup}')
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Back up and reformat existing files.')
    args = parser.parse_args()
    try:
        refresh(Path(__file__).resolve().parent.parent, apply=args.apply)
    except ValueError as error:
        raise SystemExit(str(error)) from None


if __name__ == '__main__':
    main()
