from django.contrib import admin
from .models import IngestEvent


@admin.register(IngestEvent)
class IngestEventAdmin(admin.ModelAdmin):
    list_display = ['id', 'source_system', 'source_sheet_id', 'source_tab', 'source_row_key', 'ingested_at']
    list_filter = ['source_system', 'source_sheet_id', 'source_tab', 'schema_version']
    search_fields = ['source_row_key', 'payload']
    readonly_fields = ['id', 'payload_hash', 'ingested_at']
    date_hierarchy = 'ingested_at'
    ordering = ['-ingested_at']
