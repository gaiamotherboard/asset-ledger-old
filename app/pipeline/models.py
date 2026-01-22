import re
import uuid
from django.db import models
from django.utils import timezone
from ingest.models import IngestEvent


# ============================================================
# SILVER LAYER - Staging/Normalized
# ============================================================

class StgShredSerial(models.Model):
    """Silver: Normalized shred log entries"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_event = models.OneToOneField(IngestEvent, on_delete=models.PROTECT, related_name='stg_shred')
    
    # Extracted fields
    batch_id = models.CharField(max_length=200, blank=True)
    batch_date = models.DateField(null=True, blank=True)
    client = models.CharField(max_length=200, blank=True)
    location = models.CharField(max_length=200, blank=True)
    tech = models.CharField(max_length=200, blank=True)
    
    # Serial normalization
    serial_raw = models.CharField(max_length=500, blank=True)
    serial_norm = models.CharField(max_length=500, blank=True, db_index=True,
                                   help_text="Normalized: trim, uppercase, strip trailing punctuation")
    
    dedupe_key = models.CharField(max_length=500, blank=True)
    event_time = models.DateTimeField(null=True, blank=True)
    
    # Validation
    is_valid = models.BooleanField(default=True)
    validation_errors = models.JSONField(default=list, blank=True)
    
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'stg_shred_serial'
        indexes = [
            models.Index(fields=['serial_norm']),
            models.Index(fields=['batch_id']),
        ]

    def __str__(self):
        return f"Shred: {self.serial_norm} (batch {self.batch_id})"


class StgDriveRemoval(models.Model):
    """Silver: Normalized drive removal log entries"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_event = models.OneToOneField(IngestEvent, on_delete=models.PROTECT, related_name='stg_removal')
    
    # Extracted fields
    client = models.CharField(max_length=200, blank=True)
    
    # Computer serial
    computer_serial_raw = models.CharField(max_length=500, blank=True)
    computer_serial_norm = models.CharField(max_length=500, blank=True)
    
    # Drive serial normalization
    drive_serial_raw = models.CharField(max_length=500, blank=True)
    drive_serial_norm = models.CharField(max_length=500, blank=True, db_index=True)
    
    notes = models.TextField(blank=True)
    tech_email = models.EmailField(blank=True)
    event_time = models.DateTimeField(null=True, blank=True)
    
    # Validation
    is_valid = models.BooleanField(default=True)
    validation_errors = models.JSONField(default=list, blank=True)
    
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'stg_drive_removal'
        indexes = [
            models.Index(fields=['drive_serial_norm']),
        ]

    def __str__(self):
        return f"Removal: {self.drive_serial_norm} from {self.computer_serial_norm}"


# ============================================================
# GOLD LAYER - Canonical Entities
# ============================================================

class Drive(models.Model):
    """Gold: Canonical drive entity"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    serial_norm = models.CharField(max_length=500, unique=True, db_index=True)
    first_seen_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'drive'
        ordering = ['serial_norm']

    def __str__(self):
        return self.serial_norm


class Batch(models.Model):
    """Gold: Shred batch entity"""
    batch_id = models.CharField(max_length=200, primary_key=True)
    batch_date = models.DateField(null=True, blank=True)
    client = models.CharField(max_length=200, blank=True)
    location = models.CharField(max_length=200, blank=True)
    tech = models.CharField(max_length=200, blank=True)
    first_seen_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'batch'
        ordering = ['-batch_date']

    def __str__(self):
        return self.batch_id


class DriveEvent(models.Model):
    """Gold: Drive lifecycle events"""
    EVENT_TYPE_CHOICES = [
        ('REMOVED', 'Drive Removed'),
        ('SHREDDED', 'Drive Shredded'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    drive = models.ForeignKey(Drive, on_delete=models.PROTECT, related_name='events')
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES)
    event_time = models.DateTimeField()
    source_event = models.ForeignKey(IngestEvent, on_delete=models.PROTECT,
                                    help_text="Provenance back to bronze")
    
    # Event-specific fields
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, null=True, blank=True,
                             help_text="For SHREDDED events")
    client = models.CharField(max_length=200, blank=True)
    computer_serial = models.CharField(max_length=500, blank=True,
                                      help_text="For REMOVED events")
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'drive_event'
        constraints = [
            models.UniqueConstraint(
                fields=['source_event', 'event_type'],
                name='unique_drive_event_per_source'
            )
        ]
        indexes = [
            models.Index(fields=['event_type', 'event_time']),
        ]
        ordering = ['-event_time']

    def __str__(self):
        return f"{self.drive.serial_norm} - {self.event_type} at {self.event_time}"


# ============================================================
# MATCHING AS PRODUCT
# ============================================================

class MatchDecision(models.Model):
    """Explicit matching decisions between removals and shreds"""
    DECISION_CHOICES = [
        ('MATCH', 'Match'),
        ('NO_MATCH', 'No Match'),
        ('AMBIGUOUS', 'Ambiguous'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    drive = models.ForeignKey(Drive, on_delete=models.PROTECT, related_name='match_decisions')
    
    removed_event = models.ForeignKey(DriveEvent, on_delete=models.PROTECT,
                                     related_name='match_as_removal',
                                     null=True, blank=True)
    shredded_event = models.ForeignKey(DriveEvent, on_delete=models.PROTECT,
                                      related_name='match_as_shred',
                                      null=True, blank=True)
    
    decision = models.CharField(max_length=20, choices=DECISION_CHOICES)
    rule_version = models.CharField(max_length=100, default='strict_serial_v1')
    confidence = models.DecimalField(max_digits=3, decimal_places=2,
                                    help_text="0.0 to 1.0")
    reason = models.TextField()
    decided_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'match_decision'
        indexes = [
            models.Index(fields=['decision']),
            models.Index(fields=['drive', 'decision']),
        ]
        ordering = ['-decided_at']

    def __str__(self):
        return f"{self.drive.serial_norm} - {self.decision} (confidence {self.confidence})"
