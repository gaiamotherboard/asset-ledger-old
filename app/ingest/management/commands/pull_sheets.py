import json
import os
from datetime import datetime
from django.core.management.base import BaseCommand
from django.db import IntegrityError
from google.oauth2 import service_account
from googleapiclient.discovery import build
from ingest.models import IngestEvent


class Command(BaseCommand):
    help = 'Pull data from Google Sheets and ingest into Bronze layer'

    def handle(self, *args, **options):
        # Load configuration
        config_json = os.environ.get('LEDGER_SHEETS_CONFIG', '[]')
        try:
            sheets_config = json.loads(config_json)
        except json.JSONDecodeError as e:
            self.stderr.write(self.style.ERROR(f'Invalid LEDGER_SHEETS_CONFIG JSON: {e}'))
            return

        if not sheets_config:
            self.stdout.write(self.style.WARNING('No sheets configured in LEDGER_SHEETS_CONFIG'))
            return

        # Load Google credentials
        credentials_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
        if not credentials_path or not os.path.exists(credentials_path):
            self.stderr.write(self.style.ERROR(f'Google credentials not found at: {credentials_path}'))
            return

        credentials = service_account.Credentials.from_service_account_file(
            credentials_path,
            scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
        )
        service = build('sheets', 'v4', credentials=credentials)

        total_inserted = 0
        total_duplicates = 0

        # Process each configured sheet
        for sheet_config in sheets_config:
            name = sheet_config.get('name')
            sheet_id = sheet_config.get('sheet_id')
            tab = sheet_config.get('tab')
            header_row = sheet_config.get('header_row', 1)

            if not all([name, sheet_id, tab]):
                self.stderr.write(self.style.ERROR(f'Invalid config: {sheet_config}'))
                continue

            self.stdout.write(f'Pulling {name} from {sheet_id}:{tab}...')

            try:
                # Fetch the data
                range_name = f'{tab}!A{header_row}:ZZ'
                result = service.spreadsheets().values().get(
                    spreadsheetId=sheet_id,
                    range=range_name
                ).execute()

                values = result.get('values', [])
                if not values:
                    self.stdout.write(self.style.WARNING(f'  No data found in {name}'))
                    continue

                # First row is headers
                headers = values[0]
                data_rows = values[1:]

                inserted = 0
                duplicates = 0

                # Process each data row
                for idx, row in enumerate(data_rows, start=header_row + 1):
                    # Pad row to match header length
                    while len(row) < len(headers):
                        row.append('')

                    # Create payload dict
                    payload = {header: value for header, value in zip(headers, row)}

                    # Compute hash
                    payload_hash = IngestEvent.compute_payload_hash(payload)

                    # Create source_row_key (absolute row number in tab)
                    source_row_key = f'{sheet_id}:{tab}:{idx}'

                    # Parse timestamp if present
                    source_timestamp = None
                    timestamp_value = payload.get('Timestamp') or payload.get('timestamp')
                    if timestamp_value:
                        try:
                            # Try parsing common formats
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
                            payload=payload,
                            payload_hash=payload_hash,
                            schema_version='v1'
                        )
                        inserted += 1
                    except IntegrityError:
                        # Duplicate - already exists
                        duplicates += 1

                self.stdout.write(self.style.SUCCESS(
                    f'  {name}: {inserted} inserted, {duplicates} duplicates'
                ))
                total_inserted += inserted
                total_duplicates += duplicates

            except Exception as e:
                self.stderr.write(self.style.ERROR(f'  Error pulling {name}: {e}'))

        self.stdout.write(self.style.SUCCESS(
            f'Total: {total_inserted} inserted, {total_duplicates} duplicates'
        ))
