# Generated migration

from django.db import migrations, models
import django.utils.timezone
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='IngestEvent',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('source_system', models.CharField(db_index=True, default='google_sheets', max_length=100)),
                ('source_sheet_id', models.CharField(db_index=True, max_length=200)),
                ('source_tab', models.CharField(db_index=True, max_length=200)),
                ('source_row_key', models.CharField(db_index=True, help_text='e.g., SHEETID:TabName:RowNumber', max_length=500)),
                ('source_timestamp', models.DateTimeField(blank=True, help_text='Parsed from sheet Timestamp column if present', null=True)),
                ('payload', models.JSONField(help_text='Raw row dict')),
                ('payload_hash', models.CharField(db_index=True, help_text='SHA256 of canonical JSON payload', max_length=64)),
                ('schema_version', models.CharField(default='v1', max_length=50)),
                ('ingested_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
            ],
            options={
                'db_table': 'ingest_event',
                'ordering': ['-ingested_at'],
            },
        ),
        migrations.AddIndex(
            model_name='ingestevent',
            index=models.Index(fields=['-ingested_at'], name='ingest_even_ingeste_idx'),
        ),
        migrations.AddConstraint(
            model_name='ingestevent',
            constraint=models.UniqueConstraint(fields=('source_system', 'source_sheet_id', 'source_tab', 'source_row_key', 'payload_hash'), name='unique_ingest_event'),
        ),
    ]
