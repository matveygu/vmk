from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, FileResponse
from django.conf import settings
from django.db.models import Count
import os
from urllib.parse import quote
from main.admin_access import role_required
from .models import Material, MaterialFolder
from .forms import MaterialUploadForm, MaterialEditForm


def is_headman_or_above(user):
    return user.role in ['headman', 'teacher', 'admin']


def is_teacher_or_admin_or_uploader(user):
    """Used for materials actions: allow teachers, admins and uploaders."""
    return user.role in ['teacher', 'admin', 'uploader']


@login_required
def materials_view(request):
    """Redirect legacy materials landing to Drive root"""
    return redirect('materials_drive_root')


@login_required
def legacy_materials_redirect(request, *args, **kwargs):
    """Unified redirect for all legacy material URLs"""
    return redirect('materials_drive_root')


@role_required(is_teacher_or_admin_or_uploader)
def upload_material(request):
    if request.method == 'POST':
        form = MaterialUploadForm(request.POST, request.FILES)
        if form.is_valid():
            material = form.save(commit=False)
            material.uploaded_by = request.user

            # Создаем папку если указана новая
            folder_name = request.POST.get('new_folder', '').strip()
            if folder_name:
                parent_id = request.POST.get('folder') or request.GET.get('folder') or request.session.get('selected_folder_id')
                parent_folder = None
                if parent_id:
                    try:
                        parent_folder = MaterialFolder.objects.get(id=parent_id)
                    except MaterialFolder.DoesNotExist:
                        parent_folder = None
                folder, created = MaterialFolder.objects.get_or_create(
                    name=folder_name,
                    defaults={
                        'created_by': request.user,
                    }
                )
                if parent_folder and folder.parent_folder_id is None:
                    folder.parent_folder = parent_folder
                    folder.save(update_fields=['parent_folder'])
                material.folder = folder

            # Если папка не выбрана явно, использовать выбранную папку из сессии
            if not material.folder_id:
                selected_id = request.POST.get('folder') or request.GET.get('folder') or request.session.get('selected_folder_id')
                if selected_id:
                    try:
                        material.folder = MaterialFolder.objects.get(id=selected_id)
                    except MaterialFolder.DoesNotExist:
                        pass

            material.save()
            messages.success(request, "Материал успешно загружен")
            redirect_folder = request.POST.get('folder') or request.GET.get('folder') or request.session.get('selected_folder_id')
            if redirect_folder:
                return redirect('materials_drive_folder', folder_id=redirect_folder)
            return redirect('materials_drive_root')
        else:
            all_errors = [e for f in form for e in f.errors] + list(form.non_field_errors())
            if all_errors:
                messages.error(request, all_errors[0])
    else:
        # Предзаполнить форму выбранной папкой из GET или сессии
        selected_folder = None
        selected_id = request.GET.get('folder') or request.session.get('selected_folder_id')
        if selected_id:
            try:
                selected_folder = MaterialFolder.objects.get(id=selected_id)
            except MaterialFolder.DoesNotExist:
                selected_folder = None
        initial = {
        }
        if selected_folder:
            initial['folder'] = selected_folder.id
        form = MaterialUploadForm(initial=initial)

    # Получаем доступные папки для выбора
    folders = MaterialFolder.objects.all()

    context = {
        'form': form,
        'folders': folders,
        'selected_folder': selected_folder if 'selected_folder' in locals() else None,
    }
    return render(request, 'upload.html', context)


@login_required
def download_material(request, material_id):
    material = get_object_or_404(Material, id=material_id)

    if material.file:
        # Prefer the user-visible name stored in the record, fall back to actual file name
        ext = os.path.splitext(material.file.name)[1]
        filename = material.name or os.path.basename(material.file.name)
        # Ensure extension is present
        if ext and not filename.lower().endswith(ext.lower()):
            filename += ext
        response = FileResponse(material.file.open(), as_attachment=True)
        # RFC 5987 filename* for unicode, plus safe fallback
        # Use quote() for proper UTF-8 encoding of non-ASCII characters
        filename_encoded = quote(filename.encode('utf-8'), safe='')
        response['Content-Disposition'] = (
            f"attachment; filename*=UTF-8''{filename_encoded}"
        )
        return response
    else:
        return render(request, 'not_found.html', status=404)


@login_required
def view_material(request, material_id):
    material = get_object_or_404(Material.objects.select_related('uploaded_by', 'folder'), id=material_id)
    
    # Список поддерживаемых видеоформатов
    video_formats = ['.mp4', '.webm', '.ogg', '.mov', '.avi', '.mkv', '.flv', '.m3u8']
    audio_formats = ['.mp3', '.wav', '.ogg', '.aac', '.flac']
    image_formats = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
    document_formats = ['.pdf', '.djvu']
    # Plain-text preview only - files are read and displayed as escaped text,
    # never executed or compiled.
    text_formats = [
        '.txt', '.md', '.csv', '.log',
        '.asm', '.s', '.c', '.h', '.cpp', '.cc', '.cxx', '.hpp',
        '.py', '.pyw', '.java', '.kt', '.js', '.ts', '.cs', '.go', '.rs',
        '.rb', '.php', '.pl', '.sql', '.sh', '.bat', '.ps1',
        '.html', '.css', '.json', '.xml', '.yaml', '.yml',
        '.m', '.r', '.hs', '.lisp', '.scm',
    ]
    
    file_ext = os.path.splitext(material.file.name)[1].lower()
    
    # Определяем тип медиа
    media_type = None
    if file_ext in video_formats:
        media_type = 'video'
    elif file_ext in audio_formats:
        media_type = 'audio'
    elif file_ext in image_formats:
        media_type = 'image'
    elif file_ext in document_formats:
        media_type = 'document'
    elif file_ext in text_formats:
        media_type = 'text'
    
    # Для видео и аудио используем stream, для изображений просто показываем
    if material.file:
        file_url = material.file.url
        # if it's a text file, read its contents for inline display
        text_content = None
        text_truncated = False
        if media_type == 'text':
            try:
                # Bound memory use and always close the file after rendering a preview.
                preview_limit = 1024 * 1024
                with material.file.open('rb') as source:
                    raw = source.read(preview_limit + 1)
                text_truncated = len(raw) > preview_limit
                raw = raw[:preview_limit]
                if isinstance(raw, bytes):
                    text_content = raw.decode('utf-8', errors='replace')
                else:
                    text_content = str(raw)
            except Exception:
                text_content = None
        context = {
            'material': material,
            'media_type': media_type,
            'file_url': file_url,
            'text_content': text_content,
            'text_truncated': text_truncated,
        }
        return render(request, 'view_material.html', context)
    else:
        return render(request, 'not_found.html', status=404)

@role_required(is_teacher_or_admin_or_uploader)
def delete_material(request, material_id):
    material = get_object_or_404(Material, id=material_id)
    # capture folder before deletion so we can redirect back
    redirect_folder = material.folder_id or request.session.get('selected_folder_id')

    if request.method == 'POST':
        if material.file:
            try:
                material.file.storage.delete(material.file.name)
            except Exception:
                pass
        material.delete()
        messages.success(request, 'Домашка успешно удалена')

    # stay in the same folder if possible
    if redirect_folder:
        return redirect('materials_drive_folder', folder_id=redirect_folder)
    return redirect('materials_drive_root')


@role_required(is_teacher_or_admin_or_uploader)
def edit_material(request, material_id):
    material = get_object_or_404(Material, id=material_id)
    if request.method == 'POST':
        form = MaterialEditForm(request.POST, request.FILES, instance=material)
        if form.is_valid():
            # If replace_file is False, keep existing file
            replace = form.cleaned_data.get('replace_file')
            if not replace and 'file' in form.changed_data:
                material.file = material.__class__.objects.get(pk=material.pk).file
            form.save()
            messages.success(request, 'Материал обновлён')
            # Redirect back to current folder if any
            redirect_folder = material.folder_id or request.session.get('selected_folder_id')
            if redirect_folder:
                return redirect('materials_drive_folder', folder_id=redirect_folder)
            return redirect('materials_drive_root')
    else:
        form = MaterialEditForm(instance=material)
    return render(request, 'edit_material.html', {'form': form, 'material': material})


@role_required(is_teacher_or_admin_or_uploader)
def rename_folder(request, folder_id):
    folder = get_object_or_404(MaterialFolder, id=folder_id)
    if request.method == 'POST':
        new_name = request.POST.get('name', '').strip()
        if new_name:
            folder.name = new_name
            folder.save(update_fields=['name'])
            messages.success(request, 'Папка переименована')
        else:
            messages.error(request, 'Название папки не может быть пустым')
        parent_id = folder.parent_folder_id
        return redirect('materials_drive_folder', folder_id=(parent_id or folder.id))
    # GET -> show edit form
    return render(request, 'edit_folder.html', {'folder': folder})


@role_required(is_teacher_or_admin_or_uploader)
def delete_folder(request, folder_id):
    folder = get_object_or_404(MaterialFolder, id=folder_id)
    parent_id = folder.parent_folder_id
    if request.method == 'POST':
        # Delete all materials in this folder (files removed via Material delete)
        Material.objects.filter(folder=folder).delete()
        folder.delete()
        messages.success(request, 'Папка удалена')
        if parent_id:
            return redirect('materials_drive_folder', folder_id=parent_id)
        return redirect('materials_drive_root')
    # GET confirm page
    return render(request, 'delete_folder.html', {'folder': folder, 'parent_id': parent_id})


@role_required(is_teacher_or_admin_or_uploader)
def edit_folder(request, folder_id):
    folder = get_object_or_404(MaterialFolder, id=folder_id)
    if request.method == 'POST':
        new_name = request.POST.get('name', '').strip()
        if new_name:
            folder.name = new_name
            folder.save(update_fields=['name'])
            messages.success(request, 'Папка обновлена')
            return redirect('materials_drive_folder', folder_id=folder.id)
        messages.error(request, 'Название папки не может быть пустым')
    return render(request, 'edit_folder.html', {'folder': folder})


def _annotate_folder_stats(folders):
    if not folders:
        return folders
    by_id = {folder.pk: folder for folder in folders}
    child_counts = dict(MaterialFolder.objects.filter(parent_folder_id__in=by_id)
                        .order_by().values('parent_folder_id').annotate(total=Count('pk'))
                        .values_list('parent_folder_id', 'total'))
    for folder in folders:
        folder.material_count = child_counts.get(folder.pk, 0)
        folder.material_size = 0
    # Two batched queries instead of three queries for every displayed folder.
    for material in Material.objects.filter(folder_id__in=by_id).only('folder_id', 'file').iterator(chunk_size=500):
        folder = by_id[material.folder_id]
        folder.material_count += 1
        try:
            folder.material_size += material.file.size or 0
        except (OSError, ValueError):
            pass
    return folders


def _annotate_material_sizes(materials):
    for m in materials:
        try:
            m.size = m.file.size
        except Exception:
            m.size = 0
    return materials


# Drive-like browsing
@login_required
def drive_root(request):
    # Clear selected folder at root
    if request.session.get('selected_folder_id') is not None:
        request.session['selected_folder_id'] = None

    query = request.GET.get('q', '').strip()
    if query:
        # Search looks across the whole drive, not just the top level
        folders = MaterialFolder.objects.filter(name__icontains=query).order_by('name')
        materials = Material.objects.filter(name__icontains=query).order_by('-upload_date')
    else:
        folders = MaterialFolder.objects.filter(parent_folder__isnull=True).order_by('name')
        materials = Material.objects.filter(folder__isnull=True).order_by('-upload_date')

    materials = _annotate_material_sizes(list(materials))
    folders = _annotate_folder_stats(list(folders))
    total_items = len(folders) + len(materials)

    context = {
        'current_folder': None,
        'subfolders': folders,
        'materials': materials,
        'breadcrumbs': [],
        'can_manage': is_teacher_or_admin_or_uploader(request.user),
        'current_selected_folder': None,
        'total_items': total_items,
        'query': query,
    }
    return render(request, 'drive.html', context)


@login_required
def drive_folder(request, folder_id: int):
    folder = get_object_or_404(MaterialFolder, id=folder_id)
    # Persist current folder selection in session
    if request.session.get('selected_folder_id') != folder.id:
        request.session['selected_folder_id'] = folder.id

    query = request.GET.get('q', '').strip()
    if query:
        subfolders = MaterialFolder.objects.filter(name__icontains=query).order_by('name')
        materials = Material.objects.filter(name__icontains=query).order_by('-upload_date')
    else:
        subfolders = MaterialFolder.objects.filter(parent_folder=folder).order_by('name')
        materials = Material.objects.filter(folder=folder).order_by('-upload_date')

    materials = _annotate_material_sizes(list(materials))
    subfolders = _annotate_folder_stats(list(subfolders))
    total_items = len(subfolders) + len(materials)

    # Build breadcrumbs up the tree
    breadcrumbs = []
    current = folder
    while current is not None:
        breadcrumbs.append(current)
        current = current.parent_folder
    breadcrumbs.reverse()

    context = {
        'current_folder': folder,
        'subfolders': subfolders,
        'materials': materials,
        'breadcrumbs': breadcrumbs,
        'can_manage': is_teacher_or_admin_or_uploader(request.user),
        'current_selected_folder': folder,
        'total_items': total_items,
        'query': query,
    }
    return render(request, 'drive.html', context)


@role_required(is_teacher_or_admin_or_uploader)
def create_folder(request, parent_id: int = None):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()

        parent_folder = None
        if parent_id:
            parent_folder = get_object_or_404(MaterialFolder, id=parent_id)
        else:
            selected_id = request.session.get('selected_folder_id')
            if selected_id:
                parent_folder = get_object_or_404(MaterialFolder, id=selected_id)

        if not name:
            messages.error(request, 'Введите название папки')
            if parent_folder:
                return redirect('materials_drive_folder', folder_id=parent_folder.id)
            return redirect('materials_drive_root')

        folder = MaterialFolder.objects.create(
            name=name,
            parent_folder=parent_folder,
            created_by=request.user,
        )
        messages.success(request, 'Папка создана')
        return redirect('materials_drive_folder', folder_id=folder.id)

    # GET fallback
    if parent_id:
        return redirect('materials_drive_folder', folder_id=parent_id)
    return redirect('materials_drive_root')
