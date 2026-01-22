from django.db import transaction
from django.utils import timezone
from pipeline.models import (
    StgShredSerial, StgDriveRemoval,
    Drive, Batch, DriveEvent
)


def promote_all_valid():
    """
    Promote valid Silver entries to Gold layer.
    Returns counts of promoted records.
    """
    # Get unpromoted valid staging records
    unpromoted_shreds = StgShredSerial.objects.filter(
        is_valid=True,
        source_event__driveevent__isnull=True
    ).select_related('source_event')
    
    unpromoted_removals = StgDriveRemoval.objects.filter(
        is_valid=True,
        source_event__driveevent__isnull=True
    ).select_related('source_event')
    
    shred_count = 0
    removal_count = 0
    
    # Promote shreds
    for stg in unpromoted_shreds:
        promote_shred(stg)
        shred_count += 1
    
    # Promote removals
    for stg in unpromoted_removals:
        promote_removal(stg)
        removal_count += 1
    
    return shred_count, removal_count


def promote_shred(stg_shred):
    """Promote a shred staging record to Gold."""
    if not stg_shred.serial_norm:
        return  # Skip empty serials
    
    with transaction.atomic():
        # Upsert Drive
        drive, created = Drive.objects.get_or_create(
            serial_norm=stg_shred.serial_norm,
            defaults={'first_seen_at': timezone.now()}
        )
        if not created:
            drive.last_seen_at = timezone.now()
            drive.save(update_fields=['last_seen_at'])
        
        # Upsert Batch
        batch = None
        if stg_shred.batch_id:
            batch, batch_created = Batch.objects.get_or_create(
                batch_id=stg_shred.batch_id,
                defaults={
                    'batch_date': stg_shred.batch_date,
                    'client': stg_shred.client,
                    'location': stg_shred.location,
                    'tech': stg_shred.tech,
                    'first_seen_at': timezone.now()
                }
            )
            if not batch_created:
                # Update batch info with latest data
                batch.batch_date = stg_shred.batch_date or batch.batch_date
                batch.client = stg_shred.client or batch.client
                batch.location = stg_shred.location or batch.location
                batch.tech = stg_shred.tech or batch.tech
                batch.last_seen_at = timezone.now()
                batch.save(update_fields=['batch_date', 'client', 'location', 'tech', 'last_seen_at'])
        
        # Create DriveEvent (idempotent via unique constraint)
        DriveEvent.objects.get_or_create(
            source_event=stg_shred.source_event,
            event_type='SHREDDED',
            defaults={
                'drive': drive,
                'event_time': stg_shred.event_time or timezone.now(),
                'batch': batch,
                'client': stg_shred.client,
            }
        )


def promote_removal(stg_removal):
    """Promote a removal staging record to Gold."""
    if not stg_removal.drive_serial_norm:
        return  # Skip empty serials
    
    with transaction.atomic():
        # Upsert Drive
        drive, created = Drive.objects.get_or_create(
            serial_norm=stg_removal.drive_serial_norm,
            defaults={'first_seen_at': timezone.now()}
        )
        if not created:
            drive.last_seen_at = timezone.now()
            drive.save(update_fields=['last_seen_at'])
        
        # Create DriveEvent (idempotent via unique constraint)
        DriveEvent.objects.get_or_create(
            source_event=stg_removal.source_event,
            event_type='REMOVED',
            defaults={
                'drive': drive,
                'event_time': stg_removal.event_time or timezone.now(),
                'client': stg_removal.client,
                'computer_serial': stg_removal.computer_serial_norm,
                'notes': stg_removal.notes,
            }
        )
