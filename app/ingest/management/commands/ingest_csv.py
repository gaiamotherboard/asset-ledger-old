import csv
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError
from ingest.models import IngestEvent


class Command(BaseCommand):
    help = 'Ingest CSV file into Bronze layer (for testing)'

    def add_arguments(self, parser):
        parser.add_argument('--source', type=str, required=True, help='Source name (e.g., shred_log_serials)')
        parser.add_argument('--file', type=str, required=True, help='CSV file path')

    def handle(self, *args, **options):
        source_name = options['source']
        file_path = options['file']

        # Use source_name as both sheet_id and tab for CSV ingestion
        sheet_id = f'csv_{source_name}'
        tab = 'data'

        self.stdout.write(f'Ingesting {file_path} as source {source_name}...')

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                inserted = 0
                duplicates = 0
                row_num = 2  # Start at 2 (1 is header)

                for row_dict in reader:
                    # Compute hash
                    payload_hash = IngestEvent.compute_payload_hash(row_dict)

                    # Create source_row_key
                    source_row_key = f'{sheet_id}:{tab}:{row_num}'

                    # Parse timestamp if present
                    source_timestamp = None
                    timestamp_value = row_dict.get('Timestamp') or row_dict.get('timestamp')
                    if timestamp_value:
                        try:
                            for fmt in ['%Y-%m-%d %H:%M:%S', '%m/%d/%Y %H:%M:%S', '%Y-%m-%dT%H:%M:%S']:
                                try:
                                    source_timestamp = datetime.strptime(timestamp_value, fmt)
                                    break
                                except ValueError:
                                    continue
                        except Exception:
                            pass

                    # Try to insert
                    try:
                        IngestEvent.objects.create(
                            source_system='google_sheets',
                            source_sheet_id=sheet_id,
                            source_tab=tab,
                            source_row_key=source_row_key,
                            source_timestamp=source_timestamp,
                            payload=row_dict,
                            payload_hash=payload_hash,
                            schema_version='v1'
                        )
                        inserted += 1
                    except IntegrityError:
                        duplicates += 1

                    row_num += 1

                self.stdout.write(self.style.SUCCESS(
                    f'{source_name}: {inserted} inserted, {duplicates} duplicates'
                ))

        except FileNotFoundError:
            raise CommandError(f'File not found: {file_path}')
        except Exception as e:
            raise CommandError(f'Error reading CSV: {e}')
