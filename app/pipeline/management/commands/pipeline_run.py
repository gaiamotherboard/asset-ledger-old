from django.core.management.base import BaseCommand
from pipeline.stage import stage_all_new
from pipeline.promote import promote_all_valid
from pipeline.match import run_matching


class Command(BaseCommand):
    help = 'Run the full pipeline: Stage -> Promote -> Match'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('=== Starting Pipeline Run ==='))
        
        # Stage: Bronze -> Silver
        self.stdout.write('Stage: Processing new IngestEvents...')
        shred_count, removal_count = stage_all_new()
        self.stdout.write(self.style.SUCCESS(
            f'  Staged: {shred_count} shreds, {removal_count} removals'
        ))
        
        # Promote: Silver -> Gold
        self.stdout.write('Promote: Creating Gold entities and events...')
        promoted_shreds, promoted_removals = promote_all_valid()
        self.stdout.write(self.style.SUCCESS(
            f'  Promoted: {promoted_shreds} shreds, {promoted_removals} removals'
        ))
        
        # Match: Create match decisions
        self.stdout.write('Match: Running strict matching v1...')
        decisions_made = run_matching()
        self.stdout.write(self.style.SUCCESS(
            f'  Match decisions made: {decisions_made}'
        ))
        
        self.stdout.write(self.style.SUCCESS('=== Pipeline Run Complete ==='))
