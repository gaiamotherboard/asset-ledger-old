from django.contrib import admin
from .models import (
    StgShredSerial, StgDriveRemoval,
    Drive, Batch, DriveEvent, MatchDecision
)


# Silver layer
@admin.register(StgShredSerial)
class StgShredSerialAdmin(admin.ModelAdmin):
    list_display = ['serial_norm', 'batch_id', 'client', 'is_valid', 'created_at']
    list_filter = ['is_valid', 'client', 'batch_id']
    search_fields = ['serial_raw', 'serial_norm', 'batch_id']
    readonly_fields = ['id', 'source_event', 'created_at']


@admin.register(StgDriveRemoval)
class StgDriveRemovalAdmin(admin.ModelAdmin):
    list_display = ['drive_serial_norm', 'computer_serial_norm', 'client', 'is_valid', 'created_at']
    list_filter = ['is_valid', 'client']
    search_fields = ['drive_serial_raw', 'drive_serial_norm', 'computer_serial_raw']
    readonly_fields = ['id', 'source_event', 'created_at']


# Gold layer
@admin.register(Drive)
class DriveAdmin(admin.ModelAdmin):
    list_display = ['serial_norm', 'first_seen_at', 'last_seen_at']
    search_fields = ['serial_norm']
    readonly_fields = ['id', 'first_seen_at', 'last_seen_at']


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ['batch_id', 'batch_date', 'client', 'location']
    list_filter = ['client', 'location']
    search_fields = ['batch_id', 'client']
    readonly_fields = ['first_seen_at', 'last_seen_at']


@admin.register(DriveEvent)
class DriveEventAdmin(admin.ModelAdmin):
    list_display = ['drive', 'event_type', 'event_time', 'client', 'batch']
    list_filter = ['event_type', 'client']
    search_fields = ['drive__serial_norm', 'computer_serial', 'notes']
    readonly_fields = ['id', 'source_event', 'created_at']
    date_hierarchy = 'event_time'


@admin.register(MatchDecision)
class MatchDecisionAdmin(admin.ModelAdmin):
    list_display = ['drive', 'decision', 'confidence', 'rule_version', 'decided_at']
    list_filter = ['decision', 'rule_version']
    search_fields = ['drive__serial_norm', 'reason']
    readonly_fields = ['id', 'decided_at']
