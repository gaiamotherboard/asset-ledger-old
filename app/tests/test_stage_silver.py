import pytest
from django.core.management import call_command
from pipeline.models import StgShredSerial, StgDriveRemoval
from pipeline.normalize import normalize_serial


@pytest.mark.django_db
class TestSilverStaging:
    """Test Silver layer staging and normalization."""
    
    def test_stage_shred_serials(self):
        """Test that shred serials are staged correctly."""
        # Ingest test data
        call_command('ingest_csv',
                    source='shred_log_serials',
                    file='sample_data/shred_log_serials.csv')
        
        # Run pipeline
        call_command('pipeline_run')
        
        # Check staging
        staged = StgShredSerial.objects.all()
        assert staged.count() > 0, "Should have staged shred records"
        
        # Check for trailing punctuation normalization
        z9919_record = StgShredSerial.objects.filter(serial_raw__contains='Z9919D52').first()
        assert z9919_record is not None, "Should find Z9919D52 record"
        assert z9919_record.serial_norm == 'Z9919D52', \
            f"Trailing punctuation should be stripped: got {z9919_record.serial_norm}"
    
    def test_stage_drive_removals(self):
        """Test that drive removals are staged correctly."""
        call_command('ingest_csv',
                    source='drive_removal_log',
                    file='sample_data/drive_removal_log.csv')
        
        call_command('pipeline_run')
        
        staged = StgDriveRemoval.objects.all()
        assert staged.count() > 0, "Should have staged removal records"
    
    def test_url_in_computer_serial_flagged(self):
        """Test that computer serials containing URLs are flagged."""
        call_command('ingest_csv',
                    source='drive_removal_log',
                    file='sample_data/drive_removal_log.csv')
        
        call_command('pipeline_run')
        
        # Find the record with URL in computer serial
        url_record = StgDriveRemoval.objects.filter(
            computer_serial_raw__contains='www.example.com'
        ).first()
        
        assert url_record is not None, "Should find record with URL"
        assert not url_record.is_valid, "Record should be marked invalid"
        assert len(url_record.validation_errors) > 0, "Should have validation errors"
        assert any('URL' in err for err in url_record.validation_errors), \
            "Should flag URL in error message"
    
    def test_normalization_uppercase(self):
        """Test that serial normalization converts to uppercase."""
        assert normalize_serial('abc123') == 'ABC123'
        assert normalize_serial('XyZ789') == 'XYZ789'
    
    def test_normalization_trim(self):
        """Test that normalization trims whitespace."""
        assert normalize_serial('  ABC123  ') == 'ABC123'
    
    def test_normalization_trailing_punctuation(self):
        """Test that trailing punctuation is removed."""
        assert normalize_serial('ABC123.') == 'ABC123'
        assert normalize_serial('ABC123,') == 'ABC123'
        assert normalize_serial('ABC123;') == 'ABC123'
        assert normalize_serial('ABC123:') == 'ABC123'
        assert normalize_serial('ABC123. ') == 'ABC123'
