from django.contrib.auth.decorators import login_required
from django.db.models import Exists, OuterRef
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import MaterialFilterForm
from .models import Material, MaterialFavorite, MaterialFolder


def with_favorites(items, user):
    return items.annotate(is_favorite=Exists(MaterialFavorite.objects.filter(
        material_id=OuterRef('pk'), user=user)))


def catalog_query(request, folder):
    form = MaterialFilterForm(request.GET)
    materials = with_favorites(Material.objects.select_related('subject', 'folder'), request.user)
    folders = MaterialFolder.objects.all()
    valid = form.is_valid()
    values = form.cleaned_data
    filtered = bool(any(values.values())) or not valid
    if not valid:
        return form, materials.none(), folders.none(), filtered
    if values['q']:
        materials = materials.filter(name__icontains=values['q'])
        folders = folders.filter(name__icontains=values['q'])
    if values['subject']:
        materials = materials.filter(subject=values['subject'])
    if values['semester']:
        materials = materials.filter(semester=values['semester'])
    if values['material_type']:
        materials = materials.filter(type=values['material_type'])
    if values['favorites']:
        materials = materials.filter(is_favorite=True)
    if any(values[key] for key in ('subject', 'semester', 'material_type', 'favorites')):
        folders = folders.none()
    if not filtered:
        materials = materials.filter(folder=folder)
        folders = folders.filter(parent_folder=folder)
    return form, materials.order_by('-upload_date', '-pk'), folders.order_by('name', 'pk'), filtered


@login_required
@require_POST
def set_favorite(request, material_id):
    material = get_object_or_404(Material, pk=material_id)
    value = request.POST.get('favorite')
    if value == '1':
        MaterialFavorite.objects.get_or_create(user=request.user, material=material)
    elif value == '0':
        MaterialFavorite.objects.filter(user=request.user, material=material).delete()
    else:
        return HttpResponseBadRequest('Некорректный статус избранного.')
    target = request.POST.get('next', '')
    if not (target.startswith('/materials/') and url_has_allowed_host_and_scheme(
            target, allowed_hosts={request.get_host()}, require_https=request.is_secure())):
        target = reverse('view_material', args=[material.pk])
    return redirect(target)
