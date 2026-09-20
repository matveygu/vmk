"""Small, strict environment parsers; errors never include secret values."""
import os

from django.core.exceptions import ImproperlyConfigured


def env_bool(name, default=False):
    value = os.environ.get(name, str(default)).strip().lower()
    if value in ('1', 'true', 'yes', 'on'):
        return True
    if value in ('0', 'false', 'no', 'off'):
        return False
    raise ImproperlyConfigured(f'{name} must be True or False.')


def env_int(name, default, minimum=1, maximum=None):
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        raise ImproperlyConfigured(f'{name} must be an integer.') from None
    if value < minimum or (maximum is not None and value > maximum):
        raise ImproperlyConfigured(f'{name} is outside the allowed range.')
    return value


def env_csv(name, default=''):
    return list(dict.fromkeys(part.strip() for part in os.environ.get(name, default).split(',') if part.strip()))
