"""Campus timetable clock; independent of the server/browser timezone."""
from datetime import datetime, time, timedelta
import re
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

CAMPUS_TIMEZONE = ZoneInfo('Europe/Moscow')


def campus_now():
    return timezone.localtime(timezone.now(), CAMPUS_TIMEZONE)


def date_parity(day):
    week = (day - settings.SEMESTER_START_DATE).days // 7 + 1
    return 'even' if week % 2 == 0 else 'odd'


def parse_lesson_time(value):
    # Imports historically used both 09:00 and 09.00. Do not guess missing times.
    match = re.fullmatch(r'(\d{1,2})[:.](\d{2})(?::(\d{2}))?', (value or '').strip())
    if not match:
        return None
    try:
        return time(*(int(part or 0) for part in match.groups()))
    except ValueError:
        return None


def milliseconds(moment):
    return int(moment.timestamp() * 1000)


def annotate_timing(lessons, day, now):
    """Decorate already loaded rows without queries, including parallel lessons."""
    day_start = datetime.combine(day, time.min, CAMPUS_TIMEZONE)
    day_end = day_start + timedelta(days=1)
    eligible = []
    for lesson in lessons:
        lesson.timing_state = ''
        lesson.timing_label = ''
        lesson.timing_start = lesson.timing_end = ''
        lesson.timing_day_start = milliseconds(day_start)
        lesson.timing_day_end = milliseconds(day_end)
        start, end = parse_lesson_time(lesson.time), parse_lesson_time(lesson.time_end)
        if getattr(lesson, 'cancelled', False) or not start or not end or end <= start or lesson.week_parity not in ('all', date_parity(day)):
            continue
        lesson.timing_start = milliseconds(datetime.combine(day, start, CAMPUS_TIMEZONE))
        lesson.timing_end = milliseconds(datetime.combine(day, end, CAMPUS_TIMEZONE))
        eligible.append(lesson)
    if now.astimezone(CAMPUS_TIMEZONE).date() != day:
        return
    stamp = milliseconds(now)
    current = any(row.timing_start <= stamp < row.timing_end for row in eligible)
    next_start = min((row.timing_start for row in eligible if row.timing_start > stamp), default=None)
    for row in eligible:
        if stamp >= row.timing_end:
            row.timing_state, row.timing_label = 'past', 'Завершена'
        elif row.timing_start <= stamp:
            row.timing_state, row.timing_label = 'current', 'Сейчас идёт'
        elif not current and row.timing_start == next_start:
            row.timing_state, row.timing_label = 'next', 'Следующая'
