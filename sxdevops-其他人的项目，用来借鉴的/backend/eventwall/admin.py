from django.contrib import admin

from .models import EventRecord


@admin.register(EventRecord)
class EventRecordAdmin(admin.ModelAdmin):
    list_display = (
        'occurred_at',
        'module',
        'action',
        'result',
        'actor_username',
        'resource_type',
        'resource_name',
        'title',
    )
    list_filter = ('module', 'category', 'action', 'result', 'severity', 'source_type', 'is_demo')
    search_fields = ('title', 'summary', 'actor_username', 'resource_name', 'correlation_id')

