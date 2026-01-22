from decimal import Decimal
from django.db import transaction
from pipeline.models import Drive, DriveEvent, MatchDecision


def run_matching():
    """
    Run strict matching v1 on all drives.
    Creates MatchDecision records for each drive with clear results:
    - MATCH: exactly 1 REMOVED + 1 SHREDDED
    - NO_MATCH: only REMOVED or only SHREDDED (or neither)
    - AMBIGUOUS: multiple candidates
    
    Returns count of decisions made.
    """
    drives = Drive.objects.all()
    decisions_made = 0
    
    for drive in drives:
        # Check if we already have a decision for this drive with current rule version
        existing = MatchDecision.objects.filter(
            drive=drive,
            rule_version='strict_serial_v1'
        ).first()
        
        if existing:
            continue  # Already processed
        
        # Get all events for this drive
        removed_events = list(DriveEvent.objects.filter(
            drive=drive,
            event_type='REMOVED'
        ).order_by('event_time'))
        
        shredded_events = list(DriveEvent.objects.filter(
            drive=drive,
            event_type='SHREDDED'
        ).order_by('event_time'))
        
        # Apply strict matching rules
        decision_made = apply_strict_matching_v1(
            drive, removed_events, shredded_events
        )
        
        if decision_made:
            decisions_made += 1
    
    return decisions_made


def apply_strict_matching_v1(drive, removed_events, shredded_events):
    """
    Apply strict matching v1 rules:
    - Exactly 1 REMOVED + 1 SHREDDED = MATCH (confidence 1.0)
    - Only REMOVED (no SHREDDED) = NO_MATCH for removal
    - Only SHREDDED (no REMOVED) = NO_MATCH for shred
    - Multiple candidates = AMBIGUOUS
    - No events = NO_MATCH
    """
    removed_count = len(removed_events)
    shredded_count = len(shredded_events)
    
    with transaction.atomic():
        if removed_count == 1 and shredded_count == 1:
            # Perfect match
            MatchDecision.objects.create(
                drive=drive,
                removed_event=removed_events[0],
                shredded_event=shredded_events[0],
                decision='MATCH',
                rule_version='strict_serial_v1',
                confidence=Decimal('1.00'),
                reason='Exactly one removal and one shred event for this serial'
            )
            return True
        
        elif removed_count == 1 and shredded_count == 0:
            # Removal without shred
            MatchDecision.objects.create(
                drive=drive,
                removed_event=removed_events[0],
                shredded_event=None,
                decision='NO_MATCH',
                rule_version='strict_serial_v1',
                confidence=Decimal('0.00'),
                reason='Drive was removed but has no corresponding shred event'
            )
            return True
        
        elif removed_count == 0 and shredded_count == 1:
            # Shred without removal
            MatchDecision.objects.create(
                drive=drive,
                removed_event=None,
                shredded_event=shredded_events[0],
                decision='NO_MATCH',
                rule_version='strict_serial_v1',
                confidence=Decimal('0.00'),
                reason='Drive was shredded but has no corresponding removal event'
            )
            return True
        
        elif removed_count > 1 or shredded_count > 1:
            # Ambiguous - multiple events
            # Pick first of each for reference
            removed_ref = removed_events[0] if removed_events else None
            shredded_ref = shredded_events[0] if shredded_events else None
            
            MatchDecision.objects.create(
                drive=drive,
                removed_event=removed_ref,
                shredded_event=shredded_ref,
                decision='AMBIGUOUS',
                rule_version='strict_serial_v1',
                confidence=Decimal('0.50'),
                reason=f'Multiple events found: {removed_count} removals, {shredded_count} shreds'
            )
            return True
        
        elif removed_count == 0 and shredded_count == 0:
            # No events (shouldn't happen if Drive exists, but handle it)
            MatchDecision.objects.create(
                drive=drive,
                removed_event=None,
                shredded_event=None,
                decision='NO_MATCH',
                rule_version='strict_serial_v1',
                confidence=Decimal('0.00'),
                reason='Drive exists but has no recorded events'
            )
            return True
    
    return False
