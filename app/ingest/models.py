import hashlib
import json
import uuid
from django.db import models
from django.utils import timezone


class IngestEvent(models.Model):
    """
    Bronze layer: append-only raw truth from source systems.
    Idempotency enforced via unique constraint on (source_system, source_sheet_id, source_tab, source_row_key, payload_hash).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_system = models.CharField(max_length=100, default='google_sheets', db_index=True)
    source_sheet_id = models.CharField(max_length=200, db_index=True)
    source_tab = models.CharField(max_length=200, db_index=True)
    source_row_key = models.CharField(max_length=500, db_index=True,
                                     help_text="e.g., SHEETID:TabName:RowNumber")
    source_timestamp = models.DateTimeField(null=True, blank=True,
                                           help_text="Parsed from sheet Timestamp column if present")
    payload = models.JSONField(help_text="Raw row dict")
    payload_hash = models.CharField(max_length=64, db_index=True,
                                   help_text="SHA256 of canonical JSON payload")
    schema_version = models.CharField(max_length=50, default='v1')
    ingested_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = 'ingest_event'
        constraints = [
            models.UniqueConstraint(
                fields=['source_system', 'source_sheet_id', 'source_tab', 'source_row_key', 'payload_hash'],
                name='unique_ingest_event'
            )
        ]
        indexes = [
            models.Index(fields=['-ingested_at']),
        ]
        ordering = ['-ingested_at']

    def __str__(self):
        return f"{self.source_system}:{self.source_sheet_id}:{self.source_tab}:{self.source_row_key}"

    @staticmethod
    def compute_payload_hash(payload_dict):
        """Compute deterministic SHA256 hash of payload."""
        canonical_json = json.dumps(payload_dict, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()
