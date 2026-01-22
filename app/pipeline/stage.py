from datetime import datetime
from django.db import transaction
from ingest.models import IngestEvent
from pipeline.models import StgShredSerial, StgDriveRemoval
from pipeline.normalize import normalize_serial, validate_shred_row, validate_removal_row


def stage_all_new():
    """
    Process all IngestEvents that haven't been staged yet.
    Create Silver layer entries.
    """
    # Find unstaged shred events
    unstaged_shreds = IngestEvent.objects.filter(
        source_sheet_id__icontains='shred',
        stg_shred__isnull=True
    )
    
    # Find unstaged removal events
    unstaged_removals = IngestEvent.objects.filter(
        source_sheet_id__icontains='removal',
        stg_removal__isnull=True
    )
    
    shred_count = 0
    removal_count = 0
    
    # Stage shreds
    for event in unstaged_shreds:
        stage_shred_event(event)
        shred_count += 1
    
    # Stage removals
    for event in unstaged_removals:
        stage_removal_event(event)
        removal_count += 1
    
    return shred_count, removal_count


def stage_shred_event(event):
    """Stage a single shred log event to Silver."""
    payload = event.payload
    
    # Extract fields with multiple possible column names
    batch_id = payload.get('Batch ID') or payload.get('batch_id') or ''
    batch_date_str = payload.get('Batch Date') or payload.get('batch_date') or ''
    client = payload.get('Client') or payload.get('client') or ''
    location = payload.get('Location') or payload.get('location') or ''
    tech = payload.get('Tech') or payload.get('tech') or payload.get('Technician') or ''
    serial_raw = (payload.get('Serial Number') or 
                 payload.get('serial_number') or 
                 payload.get('Serial') or '')
    
    # Parse batch_date
    batch_date = None
    if batch_date_str:
        for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y']:
            try:
                batch_date = datetime.strptime(batch_date_str, fmt).date()
                break
            except ValueError:
                continue
    
    # Normalize serial
    serial_norm = normalize_serial(serial_raw)
    
    # Create dedupe key
    dedupe_key = f"{batch_id}|{serial_norm}" if batch_id and serial_norm else ''
    
    # Use source timestamp or fallback
    event_time = event.source_timestamp
    
    # Validate
    errors = validate_shred_row(payload)
    is_valid = len(errors) == 0
    
    # Create staging entry
    with transaction.atomic():
        StgShredSerial.objects.create(
            source_event=event,
            batch_id=batch_id,
            batch_date=batch_date,
            client=client,
            location=location,
            tech=tech,
            serial_raw=serial_raw,
            serial_norm=serial_norm,
            dedupe_key=dedupe_key,
            event_time=event_time,
            is_valid=is_valid,
            validation_errors=errors
        )


def stage_removal_event(event):
    """Stage a single drive removal event to Silver."""
    payload = event.payload
    
    # Extract fields
    client = payload.get('Client') or payload.get('client') or ''
    computer_serial_raw = (payload.get('Computer Serial Number') or 
                          payload.get('computer_serial') or 
                          payload.get('Computer Serial') or '')
    drive_serial_raw = (payload.get('Drive Serial Number') or 
                       payload.get('drive_serial') or 
                       payload.get('Drive Serial') or '')
    notes = payload.get('Notes') or payload.get('notes') or ''
    tech_email = payload.get('Tech Email') or payload.get('tech_email') or payload.get('Email') or ''
    
    # Normalize serials
    computer_serial_norm = normalize_serial(computer_serial_raw)
    drive_serial_norm = normalize_serial(drive_serial_raw)
    
    # Use source timestamp or fallback
    event_time = event.source_timestamp
    
    # Validate
    errors = validate_removal_row(payload)
    is_valid = len(errors) == 0
    
    # Create staging entry
    with transaction.atomic():
        StgDriveRemoval.objects.create(
            source_event=event,
            client=client,
            computer_serial_raw=computer_serial_raw,
            computer_serial_norm=computer_serial_norm,
            drive_serial_raw=drive_serial_raw,
            drive_serial_norm=drive_serial_norm,
            notes=notes,
            tech_email=tech_email,
            event_time=event_time,
            is_valid=is_valid,
            validation_errors=errors
        )
