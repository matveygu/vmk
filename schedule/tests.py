from django.test import TestCase, Client, override_settings
from django.urls import reverse
from datetime import date, timedelta
from .models import Schedule, Subject
from main.models import Group, CustomUser


class ParityScheduleTests(TestCase):
    def setUp(self):
        # create simple group, subject and teacher
        self.group = Group.objects.create(number='101', faculty='F', course=1)
        self.subject = Subject.objects.create(name='Math')
        # add three lessons same day with different parity
        for parity in ['all', 'odd', 'even']:
            Schedule.objects.create(
                faculty='F',
                group=self.group,
                day='Понедельник',
                lesson_number=1,
                time='08:00',
                time_end='09:30',
                subject=self.subject,
                classroom='101',
                week_parity=parity
            )
        self.client = Client()
        # create a normal user in the group
        self.user = CustomUser.objects.create(username='u1', name='User', role='student', student_id='s0001', faculty='F', course=1, group=self.group)
        self.user.set_password('pass')
        self.user.save()
        # use force_login to bypass authentication middleware
        self.client.force_login(self.user)

    @override_settings(SEMESTER_START_DATE=date(2026, 1, 1))
    def test_week_parity_calculation(self):
        # Monday in week 1; inspect lessons, not the always-visible filter labels.
        resp = self.client.get(reverse('schedule') + '?date=2026-01-05')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['current_parity'], 'odd')
        self.assertCountEqual([s.week_parity for s in resp.context['schedule']], ['all', 'odd'])
        resp2 = self.client.get(reverse('schedule') + '?date=2026-01-05&parity=even')
        self.assertEqual(resp2.context['current_parity'], 'even')
        self.assertCountEqual([s.week_parity for s in resp2.context['schedule']], ['all', 'even'])
