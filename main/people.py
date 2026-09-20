"""Read-only people directory: browse a group's roster or search across the portal."""
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .models import CustomUser
from .people_forms import PeopleSearchForm


@login_required
@require_GET
def people_directory(request):
    data = request.GET.copy()
    own_group_id = request.user.group_id
    if not data and own_group_id:
        # First visit with no filters yet - default to the viewer's own group.
        data['group'] = str(own_group_id)

    form = PeopleSearchForm(data)
    people = CustomUser.objects.none()
    prompt_empty = False

    if form.is_valid():
        group = form.cleaned_data['group']
        query = form.cleaned_data['q']
        if group or query:
            people = CustomUser.objects.filter(is_active=True).select_related('group').order_by('name', 'pk')
            if group:
                people = people.filter(group=group)
            if query:
                people = people.filter(Q(name__icontains=query) | Q(student_id__icontains=query))
        else:
            # Neither a group nor a query - avoid dumping the entire portal directory.
            prompt_empty = True

    query_params = data.copy()
    query_params.pop('page', None)
    page = Paginator(people, 30).get_page(request.GET.get('page'))

    return render(request, 'people.html', {
        'filter_form': form, 'page_obj': page, 'people': page.object_list,
        'filter_query': query_params.urlencode(), 'own_group_id': own_group_id,
        'prompt_empty': prompt_empty, 'has_filters': bool(query_params),
    })
