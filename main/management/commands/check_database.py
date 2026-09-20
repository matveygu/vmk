from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Readiness check: database reachable and the user table migrated.'

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1 FROM main_customuser LIMIT 1')
        self.stdout.write('Database ready')
