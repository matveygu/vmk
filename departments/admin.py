from django.contrib import admin
from .models import Department


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'abbr', 'stream', 'head', 'founded')
    list_filter = ('stream',)
    search_fields = ('name', 'abbr', 'head')
