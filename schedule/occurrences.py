"""Apply date exceptions to in-memory rows; never save the decorated rows."""
from copy import copy
from datetime import time

from .models import LessonChange
from .timing import parse_lesson_time


def apply_changes(lessons, day=None):
    if not lessons:
        return []
    dates = {day or row.row_date for row in lessons}
    changes = {(item.schedule_id, item.date): item for item in
               LessonChange.objects.filter(schedule_id__in=[row.pk for row in lessons], date__in=dates)
               .select_related('subject')}
    result = []
    for original in lessons:
        row = copy(original)
        row.change = changes.get((row.pk, day or row.row_date))
        row.cancelled = bool(row.change and row.change.cancelled)
        if row.change:
            row.subject = row.change.subject
            row.time = row.change.start.strftime('%H:%M')
            row.time_end = row.change.end.strftime('%H:%M')
            row.classroom = row.change.classroom
            row.another_classroom = ''
        result.append(row)
    return sorted(result, key=lambda row: (getattr(row, 'row_date', day),
                  parse_lesson_time(row.time) or time.max, row.lesson_number))
