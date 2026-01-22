import pytest
from django.core.management import call_command
from pipeline.models import MatchDecision, Drive


@pytest.mark.django_db
class TestMatching:
    """Test matching logic between removals and shreds."""
    
    def test_match_decisions_created(self):
        """Test that match decisions are created."""
        call_command('ingest_csv',
                    source='shred_log_serials',
                    file='sample_data/shred_log_serials.csv')
        call_command('ingest_csv',
                    source='drive_removal_log',
                    file='sample_data/drive_removal_log.csv')
        
        call_command('pipeline_run')
        
        decisions = MatchDecision.objects.all()
        assert decisions.count() > 0, "Should have created match decisions"
    
    def test_strict_match_found(self):
        """Test that drives with exactly 1 removal + 1 shred get MATCH."""
        call_command('ingest_csv',
                    source='shred_log_serials',
                    file='sample_data/shred_log_serials.csv')
        call_command('ingest_csv',
                    source='drive_removal_log',
                    file='sample_data/drive_removal_log.csv')
        
        call_command('pipeline_run')
        
        # ABC123XYZ and DEF456UVW should match (1 removal + 1 shred each)
        abc_drive = Drive.objects.filter(serial_norm='ABC123XYZ').first()
        assert abc_drive is not None
        
        abc_decision = MatchDecision.objects.filter(drive=abc_drive).first()
        assert abc_decision is not None
        assert abc_decision.decision == 'MATCH', \
            f"ABC123XYZ should MATCH, got {abc_decision.decision}"
        assert abc_decision.confidence == 1.0
        assert abc_decision.removed_event is not None
        assert abc_decision.shredded_event is not None
    
    def test_unmatched_removal(self):
        """Test that removal without shred gets NO_MATCH."""
        call_command('ingest_csv',
                    source='shred_log_serials',
                    file='sample_data/shred_log_serials.csv')
        call_command('ingest_csv',
                    source='drive_removal_log',
                    file='sample_data/drive_removal_log.csv')
        
        call_command('pipeline_run')
        
        # ORPHAN999 is removed but never shredded
        orphan_drive = Drive.objects.filter(serial_norm='ORPHAN999').first()
        assert orphan_drive is not None
        
        orphan_decision = MatchDecision.objects.filter(drive=orphan_drive).first()
        assert orphan_decision is not None
        assert orphan_decision.decision == 'NO_MATCH', \
            f"ORPHAN999 should be NO_MATCH, got {orphan_decision.decision}"
        assert orphan_decision.removed_event is not None
        assert orphan_decision.shredded_event is None
    
    def test_unmatched_shred(self):
        """Test that shred without removal gets NO_MATCH."""
        call_command('ingest_csv',
                    source='shred_log_serials',
                    file='sample_data/shred_log_serials.csv')
        call_command('ingest_csv',
                    source='drive_removal_log',
                    file='sample_data/drive_removal_log.csv')
        
        call_command('pipeline_run')
        
        # ORPHAN123 is shredded but never removed
        orphan_drive = Drive.objects.filter(serial_norm='ORPHAN123').first()
        assert orphan_drive is not None
        
        orphan_decision = MatchDecision.objects.filter(drive=orphan_drive).first()
        assert orphan_decision is not None
        assert orphan_decision.decision == 'NO_MATCH', \
            f"ORPHAN123 should be NO_MATCH, got {orphan_decision.decision}"
        assert orphan_decision.removed_event is None
        assert orphan_decision.shredded_event is not None
    
    def test_normalized_serial_matching(self):
        """Test that serials match after normalization (e.g., trailing punctuation)."""
        call_command('ingest_csv',
                    source='shred_log_serials',
                    file='sample_data/shred_log_serials.csv')
        call_command('ingest_csv',
                    source='drive_removal_log',
                    file='sample_data/drive_removal_log.csv')
        
        call_command('pipeline_run')
        
        # Z9919D52 appears with trailing period in shred log and removal log
        # Both should normalize to Z9919D52 and match
        z_drive = Drive.objects.filter(serial_norm='Z9919D52').first()
        assert z_drive is not None, "Should create drive for Z9919D52"
        
        z_decision = MatchDecision.objects.filter(drive=z_drive).first()
        assert z_decision is not None
        assert z_decision.decision == 'MATCH', \
            f"Z9919D52 should MATCH after normalization, got {z_decision.decision}"
    
    def test_all_drives_have_decisions(self):
        """Test that every drive gets a match decision."""
        call_command('ingest_csv',
                    source='shred_log_serials',
                    file='sample_data/shred_log_serials.csv')
        call_command('ingest_csv',
                    source='drive_removal_log',
                    file='sample_data/drive_removal_log.csv')
        
        call_command('pipeline_run')
        
        drive_count = Drive.objects.count()
        decision_count = MatchDecision.objects.count()
        
        assert decision_count == drive_count, \
            f"Every drive should have a decision: {drive_count} drives, {decision_count} decisions"
