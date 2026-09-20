"""End-to-end migration tests. Run with Compose against a disposable test DB."""
from io import StringIO
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from unittest import skipUnless

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TransactionTestCase, override_settings

from departments.models import Department
from main.models import CustomUser, Group
from materials.models import Material, MaterialFolder
from schedule.models import Homework, Schedule


@skipUnless(connection.vendor == 'postgresql', 'Requires real PostgreSQL')
class PostgreSQLImportTests(TransactionTestCase):
    def setUp(self):
        # The import command registers this temporary, read-only alias at runtime.
        # Permit it after Django has created the normal isolated test database.
        type(self).databases = {'default', 'sqlite_import'}
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / 'source.sqlite3'
        env = {**os.environ, 'DATABASE_ENGINE': 'sqlite', 'DATABASE_URL': '',
               'SQLITE_PATH': str(self.source), 'PORTAL_DATA_DIR': self.temp.name}
        subprocess.run([sys.executable, 'manage.py', 'migrate', '--noinput'],
                       cwd=settings.BASE_DIR, env=env, check=True, capture_output=True)
        script = '''
from main.models import CustomUser, Group, News
from django.contrib.auth.models import Group as AuthGroup, Permission
from schedule.models import Subject, Schedule, Homework
from materials.models import Material, MaterialFolder
from departments.models import Department
g = Group.objects.create(pk=51, number=105, faculty='ВМК')
u = CustomUser.objects.create_user(pk=77, username='import-user', student_id='import-user', password='MigrationTest123!', email='student@example.org', group=g, role='headman')
p = Permission.objects.get(codename='view_news')
a = AuthGroup.objects.create(name='Imported permission group')
a.permissions.add(p)
u.groups.add(a)
u.user_permissions.add(p)
s = Subject.objects.create(name='Математика')
t = Schedule.objects.create(group=g, subject=s, day='Понедельник', lesson_number=1, time='09:00', classroom='101')
Homework.objects.create(schedule=t, group=g, subject=s, created_by=u, content='Задание', file='homework/test.pdf')
f = MaterialFolder.objects.create(name='Корень', created_by=u)
child = MaterialFolder.objects.create(name='Вложенная', created_by=u, parent_folder=f)
Material.objects.create(name='Материал', file='materials/test.pdf', folder=child, uploaded_by=u)
News.objects.create(title='Новость', content='Текст', author=u)
Department.objects.filter(pk='sp').update(name='Изменённая кафедра', directions=['Тест'])
'''
        subprocess.run([sys.executable, 'manage.py', 'shell', '-c', script],
                       cwd=settings.BASE_DIR, env=env, check=True, capture_output=True)

    def run_import(self, **kwargs):
        with override_settings(DATA_DIR=Path(self.temp.name)):
            call_command('migrate_from_sqlite', str(self.source), stdout=StringIO(), **kwargs)

    def test_import_preserves_relations_passwords_and_resets_sequences(self):
        self.run_import(dry_run=True)
        self.assertFalse(CustomUser.objects.exists())
        self.run_import()
        user = CustomUser.objects.get(pk=77)
        self.assertTrue(user.check_password('MigrationTest123!'))
        self.assertEqual(user.role, 'headman')
        self.assertEqual(user.group.number, 105)
        self.assertEqual(user.email, 'student@example.org')
        self.assertEqual(user.groups.get().permissions.get().codename, 'view_news')
        self.assertEqual(user.user_permissions.get().codename, 'view_news')
        self.assertEqual(Material.objects.get().folder.parent_folder.name, 'Корень')
        self.assertEqual(Material.objects.get().file.name, 'materials/test.pdf')
        self.assertEqual(Homework.objects.get().schedule, Schedule.objects.get())
        self.assertEqual(Department.objects.get(pk='sp').directions, ['Тест'])
        self.assertGreater(CustomUser.objects.create_user(username='next', student_id='next').pk, 77)
        self.assertGreater(Group.objects.create(number=106, faculty='ВМК').pk, 51)
        with self.assertRaisesMessage(CommandError, 'Target is not empty'):
            self.run_import()
        # Original source remains unchanged, including the old SQLite identities.
        with sqlite3.connect(self.source) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM main_customuser').fetchone()[0], 1)

    def test_failed_import_rolls_back_everything(self):
        # SQLite permits oversized varchar values; PostgreSQL correctly rejects them.
        with sqlite3.connect(self.source) as db:
            db.execute('UPDATE main_news SET title = ?', ('x' * 201,))
        before = list(Department.objects.values().order_by('pk'))
        with self.assertRaisesMessage(CommandError, 'Import failed (DataError)'):
            self.run_import()
        self.assertFalse(CustomUser.objects.exists())
        self.assertFalse(Group.objects.exists())
        self.assertEqual(list(Department.objects.values().order_by('pk')), before)
