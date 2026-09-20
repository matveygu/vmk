"""Access checks for the production reverse proxy."""
from django.http import HttpResponse
from django.db import DatabaseError, connection
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe


@never_cache
@require_safe
def health(request):
    """Readiness of the serving worker and its database, without private details."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except DatabaseError:
        return HttpResponse('unavailable', status=503, content_type='text/plain')
    return HttpResponse('ok', content_type='text/plain')


@never_cache
def media_access(request):
    # Current portal policy: attachments are shared with active registered users.
    # Per-group/object permissions require a separate policy, not just this check.
    allowed = request.user.is_authenticated and request.user.is_active
    return HttpResponse(status=204 if allowed else 401)
