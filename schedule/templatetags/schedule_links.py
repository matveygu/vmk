from django import template
from django.urls import reverse

from schedule.timing import campus_now

register = template.Library()


@register.simple_tag(takes_context=True)
def today_schedule_url(context):
    # Cache within this render: all navigation links agree even at midnight.
    if '_campus_today' not in context:
        context['_campus_today'] = campus_now().date().isoformat()
    return f"{reverse('schedule')}?date={context['_campus_today']}"
