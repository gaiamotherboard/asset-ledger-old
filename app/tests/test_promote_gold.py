import pytest
from django.core.management import call_command
from pipeline.models import Drive, Batch, DriveEvent


@pytest.mark.django_db
class TestGoldPromotion:
    """Test Silver to Gold promotion."""
    
    def test_drives_created(self):
        """Test that Drive entities are created from staging."""
        call_command('ingest_csv',
                    source='shred_log_serials',
                    file='sample_data/shred_log_serials.csv')
        call_command('ingest_csv',
                    source='drive_removal_log',
                    file='sample_data/drive_removal_log.csv')
        
        call_command('pipeline_run')
        
        drives = Drive.objects.all()
        assert drives.count() > 0, "Should have created Drive entities"
        
        # Check specific drive with normalized serial
        z9919_drive = Drive.objects.filter(serial_norm='Z9919D52').first()
        assert z9919_drive is not None, "Should create drive for Z9919D52"
    
    def test_batches_created(self):
        """Test that Batch entities are created."""
        call_command('ingest_csv',
                    source='shred_log_serials',
                    file='sample_data/shred_log_serials.csv')
        
        call_command('pipeline_run')
        
        batches = Batch.objects.all()
        assert batches.count() > 0, "Should have created Batch entities"
        
        batch001 = Batch.objects.filter(batch_id='BATCH001').first()
        assert batch001 is not None, "Should create BATCH001"
        assert batch001.client == 'Acme Corp'
    
    def test_drive_events_created(self):
        """Test that DriveEvents are created for both removals and shreds."""
        call_command('ingest_csv',
                    source='shred_log_serials',
                    file='sample_data/shred_log_serials.csv')
        call_command('ingest_csv',
                    source='drive_removal_log',
                    file='sample_data/drive_removal_log.csv')
        
        call_command('pipeline_run')
        
        events = DriveEvent.objects.all()
        assert events.count() > 0, "Should have created DriveEvents"
        
        # Check for both event types
        removed_events = DriveEvent.objects.filter(event_type='REMOVED')
        shredded_events = DriveEvent.objects.filter(event_type='SHREDDED')
        
        assert removed_events.count() > 0, "Should have REMOVED events"
        assert shredded_events.count() > 0, "Should have SHREDDED events"
    
    def test_event_idempotency(self):
        """Test that running pipeline twice doesn't duplicate events."""
        call_command('ingest_csv',
                    source='shred_log_serials',
                    file='sample_data/shred_log_serials.csv')
        
        call_command('pipeline_run')
        count_first = DriveEvent.objects.count()
        
        call_command('pipeline_run')
        count_second = DriveEvent.objects.count()
        
        assert count_second == count_first, "Should not duplicate events"
