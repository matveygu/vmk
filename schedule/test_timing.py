from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from main.models import CustomUser, Group
from .models import Schedule, Subject
from .timing import CAMPUS_TIMEZONE, annotate_timing, campus_now, parse_lesson_time


@override_settings(SEMESTER_START_DATE=date(2026, 9, 21))
class LessonTimingTests(SimpleTestCase):
    day = date(2026, 9, 21)

    def rows(self):
        return [SimpleNamespace(time=start, time_end=end, week_parity='all')
                for start, end in [('09:00', '10:30'), ('10:45', '12:15'), ('13:00', '14:30')]]

    def test_transitions_at_exact_boundaries_and_breaks(self):
        cases = [(8, 0, ['next', '', '']), (9, 0, ['current', '', '']),
                 (10, 30, ['past', 'next', '']), (10, 45, ['past', 'current', '']),
                 (12, 15, ['past', 'past', 'next']), (14, 30, ['past', 'past', 'past'])]
        for hour, minute, states in cases:
            with self.subTest(hour=hour, minute=minute):
                rows = self.rows()
                annotate_timing(rows, self.day, datetime(2026, 9, 21, hour, minute, tzinfo=CAMPUS_TIMEZONE))
                self.assertEqual([row.timing_state for row in rows], states)

    def test_other_dates_are_neutral(self):
        for day in (20, 22):
            rows = self.rows()
            annotate_timing(rows, self.day, datetime(2026, 9, day, 10, tzinfo=CAMPUS_TIMEZONE))
            self.assertTrue(all(row.timing_state == '' for row in rows))

    def test_bad_times_are_neutral_and_not_guessed(self):
        for start, end in [('bad', '10:30'), ('09:00', None), ('25:00', '26:00'),
                           ('10:00', '09:00'), ('09:00', '09:00')]:
            rows = [SimpleNamespace(time=start, time_end=end, week_parity='all')]
            annotate_timing(rows, self.day, datetime(2026, 9, 21, 10, tzinfo=CAMPUS_TIMEZONE))
            self.assertEqual(rows[0].timing_state, '')
            self.assertEqual(rows[0].timing_start, '')

    def test_supported_import_time_formats(self):
        for value in ('09:00', '9:00', '09.00', '09:00:00', ' 09:00 '):
            self.assertEqual(parse_lesson_time(value).hour, 9)

    def test_parallel_lessons_and_actual_parity(self):
        rows = self.rows()
        rows[1].time, rows[1].time_end = '09:00', '10:30'
        rows[2].week_parity = 'even'
        annotate_timing(rows, self.day, datetime(2026, 9, 21, 9, tzinfo=CAMPUS_TIMEZONE))
        self.assertEqual([row.timing_state for row in rows], ['current', 'current', ''])
        self.assertEqual(rows[2].timing_start, '')

    @patch('schedule.timing.timezone.now', return_value=datetime(2026, 9, 20, 22, tzinfo=timezone.utc))
    def test_campus_date_is_moscow_not_server_utc(self, clock):
        self.assertEqual(campus_now().date(), self.day)
        self.assertEqual(campus_now().hour, 1)


@override_settings(SECURE_SSL_REDIRECT=False, SEMESTER_START_DATE=date(2026, 9, 21))
class PrivateTimetableTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.group = Group.objects.create(number=101, faculty='ВМК')
        cls.user = CustomUser.objects.create_user(username='timing-test', student_id='timing-test',
                                                  group=cls.group, faculty='ВМК', role='student')
        cls.subject = Subject.objects.create(name='Анализ')
        for number, start, end in [(1, '09:00', '10:30'), (2, '10:45', '12:15'), (3, '18:00', '19:30')]:
            Schedule.objects.create(group=cls.group, faculty='ВМК', subject=cls.subject,
                                    day='Понедельник', lesson_number=number, time=start, time_end=end,
                                    classroom='101', first_teacher_id=cls.user.student_id)

    def setUp(self):
        self.client.force_login(self.user)
        self.clock = self.enterContext(patch('schedule.timing.timezone.now',
            return_value=datetime(2026, 9, 21, 11, tzinfo=CAMPUS_TIMEZONE)))

    def test_home_and_day_have_identical_states(self):
        home = self.client.get(reverse('home'))
        day = self.client.get(reverse('schedule'), {'date': '2026-09-21'})
        for response, key in ((home, 'today_schedule'), (day, 'schedule')):
            self.assertEqual([row.timing_state for row in response.context[key]], ['past', 'current', ''])
            self.assertContains(response, 'lesson-is-past')
            self.assertContains(response, 'lesson-is-current')
            self.assertContains(response, 'Сейчас идёт')
            self.assertContains(response, 'data-server-now=')
        self.assertContains(home, '/schedule/?date=2026-09-21')
        self.assertContains(home, 'view=week')

    def test_evening_home_does_not_switch_to_tomorrow(self):
        self.clock.return_value = datetime(2026, 9, 21, 18, 10, tzinfo=CAMPUS_TIMEZONE)
        response = self.client.get(reverse('home'))
        self.assertEqual(response.context['today'], date(2026, 9, 21))
        self.assertEqual(response.context['today_schedule'][-1].timing_state, 'current')
        self.assertNotContains(response, 'Завтра в расписании')

    def test_home_shortcuts_are_compact_named_icon_links(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'class="ws-quick-icon"', count=3)
        for label in ('Расписание', 'Задания', 'Материалы'):
            self.assertContains(response, f'aria-label="{label}" title="{label}"')
        self.assertNotContains(response, 'План на день и неделю')

    def test_home_filters_wrong_week(self):
        Schedule.objects.filter(lesson_number=2).update(week_parity='even')
        response = self.client.get(reverse('home'))
        self.assertEqual([row.lesson_number for row in response.context['today_schedule']], [1, 3])
        self.assertEqual(response.context['today_schedule'][-1].timing_state, 'next')

    def test_week_highlights_only_today(self):
        Schedule.objects.create(group=self.group, faculty='ВМК', subject=self.subject,
                                day='Вторник', lesson_number=1, time='10:45', time_end='12:15', classroom='101')
        response = self.client.get(reverse('schedule'), {'date': '2026-09-22', 'view': 'week'})
        self.assertEqual([row.timing_state for row in response.context['week_schedule']], ['past', 'current', '', ''])

    def test_other_day_has_no_live_highlight(self):
        response = self.client.get(reverse('schedule'), {'date': '2026-09-28'})
        self.assertTrue(all(not row.timing_state for row in response.context['schedule']))
        self.assertNotContains(response, 'lesson-is-current')
        self.assertNotContains(response, 'lesson-is-past')

    def test_teacher_receives_only_own_lessons(self):
        self.user.role = 'teacher'
        self.user.save(update_fields=['role'])
        Schedule.objects.filter(lesson_number=2).update(first_teacher_id='other')
        for url, key in ((reverse('home'), 'today_schedule'), (reverse('schedule') + '?date=2026-09-21', 'schedule')):
            response = self.client.get(url)
            self.assertEqual([row.lesson_number for row in response.context[key]], [1, 3])

    def test_canonical_date_preserves_other_parameters(self):
        for raw in ('', 'invalid', '2026-02-30', '9999-12-31'):
            response = self.client.get(reverse('schedule'), {'date': raw, 'view': 'week', 'parity': 'all'})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(parse_qs(urlsplit(response.url).query),
                             {'date': ['2026-09-21'], 'view': ['week'], 'parity': ['all']})
        response = self.client.get(reverse('schedule'), follow=True)
        self.assertEqual(response.redirect_chain, [('/schedule/?date=2026-09-21', 302)])
        self.assertEqual(response.status_code, 200)

    def test_group_missing_still_has_canonical_date_and_today_link(self):
        self.user.group = None
        self.user.save(update_fields=['group'])
        response = self.client.get(reverse('schedule'), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'У вас не назначена группа')
        self.assertContains(response, '?date=2026-09-21&view=day')

    def test_anonymous_does_not_receive_private_timetable(self):
        self.client.logout()
        response = self.client.get(reverse('schedule'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)
        self.assertNotContains(self.client.get(reverse('home')), 'data-timetable')
