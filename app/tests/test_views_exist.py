import pytest
from django.core.management import call_command
from django.db import connection


@pytest.mark.django_db
class TestViews:
    """Test that SQL views exist and return data."""
    
    def test_views_exist(self):
        """Test that all required views exist in the database."""
        with connection.cursor() as cursor:
            # Check each view exists
            views = [
                'v_drive_lifecycle',
                'v_unmatched_removals',
                'v_unmatched_shreds',
                'v_ambiguous_matches'
            ]
            
            for view_name in views:
                cursor.execute(f"SELECT COUNT(*) FROM {view_name}")
                # Just checking it doesn't error - view exists
    
    def test_drive_lifecycle_view(self):
        """Test v_drive_lifecycle view returns data."""
        call_command('ingest_csv',
                    source='shred_log_serials',
                    file='sample_data/shred_log_serials.csv')
        call_command('ingest_csv',
                    source='drive_removal_log',
                    file='sample_data/drive_removal_log.csv')
        
        call_command('pipeline_run')
        
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM v_drive_lifecycle")
            count = cursor.fetchone()[0]
            assert count > 0, "v_drive_lifecycle should return rows"
    
    def test_unmatched_removals_view(self):
        """Test v_unmatched_removals view returns orphaned removals."""
        call_command('ingest_csv',
                    source='shred_log_serials',
                    file='sample_data/shred_log_serials.csv')
        call_command('ingest_csv',
                    source='drive_removal_log',
                    file='sample_data/drive_removal_log.csv')
        
        call_command('pipeline_run')
        
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM v_unmatched_removals")
            count = cursor.fetchone()[0]
            assert count > 0, "Should have at least one unmatched removal (ORPHAN999)"
            
            # Verify ORPHAN999 is in there
            cursor.execute("""
                SELECT serial_norm FROM v_unmatched_removals 
                WHERE serial_norm = 'ORPHAN999'
            """)
            result = cursor.fetchone()
            assert result is not None, "ORPHAN999 should be in unmatched_removals"
    
    def test_unmatched_shreds_view(self):
        """Test v_unmatched_shreds view returns orphaned shreds."""
        call_command('ingest_csv',
                    source='shred_log_serials',
                    file='sample_data/shred_log_serials.csv')
        call_command('ingest_csv',
                    source='drive_removal_log',
                    file='sample_data/drive_removal_log.csv')
        
        call_command('pipeline_run')
        
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM v_unmatched_shreds")
            count = cursor.fetchone()[0]
            assert count > 0, "Should have at least one unmatched shred (ORPHAN123)"
            
            # Verify ORPHAN123 is in there
            cursor.execute("""
                SELECT serial_norm FROM v_unmatched_shreds 
                WHERE serial_norm = 'ORPHAN123'
            """)
            result = cursor.fetchone()
            assert result is not None, "ORPHAN123 should be in unmatched_shreds"
    
    def test_ambiguous_matches_view(self):
        """Test v_ambiguous_matches view structure (may be empty with current data)."""
        call_command('ingest_csv',
                    source='shred_log_serials',
                    file='sample_data/shred_log_serials.csv')
        call_command('ingest_csv',
                    source='drive_removal_log',
                    file='sample_data/drive_removal_log.csv')
        
        call_command('pipeline_run')
        
        with connection.cursor() as cursor:
            # View should exist and be queryable (even if empty)
            cursor.execute("SELECT COUNT(*) FROM v_ambiguous_matches")
            count = cursor.fetchone()[0]
            # Count could be 0 with current sample data, just verify query works
            assert count >= 0
