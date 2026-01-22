import pytest
from django.core.management import call_command
from ingest.models import IngestEvent


@pytest.mark.django_db
class TestBronzeIdempotency:
    """Test that ingesting the same data twice doesn't create duplicates."""
    
    def test_csv_ingest_idempotency(self):
        """Ingesting same CSV twice should not create duplicates."""
        # First ingestion
        call_command('ingest_csv', 
                    source='shred_log_serials',
                    file='sample_data/shred_log_serials.csv')
        
        count_after_first = IngestEvent.objects.count()
        assert count_after_first > 0, "Should have ingested some events"
        
        # Second ingestion (same data)
        call_command('ingest_csv',
                    source='shred_log_serials',
                    file='sample_data/shred_log_serials.csv')
        
        count_after_second = IngestEvent.objects.count()
        assert count_after_second == count_after_first, \
            "Second ingestion should not create duplicates"
    
    def test_payload_hash_prevents_duplicates(self):
        """Payload hash ensures same data doesn't create duplicate records."""
        call_command('ingest_csv',
                    source='drive_removal_log',
                    file='sample_data/drive_removal_log.csv')
        
        first_count = IngestEvent.objects.count()
        
        # Ingest again
        call_command('ingest_csv',
                    source='drive_removal_log',
                    file='sample_data/drive_removal_log.csv')
        
        second_count = IngestEvent.objects.count()
        assert second_count == first_count
