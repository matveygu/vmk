"""Access checks for the production reverse proxy."""
from django.http import HttpResponse
from django.views.decorators.cache import never_cache


@never_cache
def media_access(request):
    # Current portal policy: attachments are shared with active registered users.
    # Per-group/object permissions require a separate policy, not just this check.
    allowed = request.user.is_authenticated and request.user.is_active
    return HttpResponse(status=204 if allowed else 401)
