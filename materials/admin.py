from django.contrib import admin
from .models import Material, MaterialFolder


@admin.register(MaterialFolder)
class MaterialFolderAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent_folder', 'created_by', 'created_at']
    list_filter = ['created_at']
    search_fields = ['name', 'created_by__username']
    readonly_fields = ['created_at']
    ordering = ['name']


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ['name', 'type', 'uploaded_by', 'upload_date', 'folder']
    list_filter = ['type', 'upload_date']
    search_fields = ['name', 'uploaded_by__username', ]
    readonly_fields = ['upload_date', 'type']
    ordering = ['-upload_date']

    fieldsets = (
        (None, {
            'fields': ('name', 'file', 'folder')
        }),
        ('Дополнительно', {
            'fields': ('uploaded_by', 'upload_date', 'type'),
            'classes': ('collapse',)
        }),
    )