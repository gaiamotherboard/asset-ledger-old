# Generated migration

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('ingest', '0001_initial'),
    ]

    operations = [
        # Silver models
        migrations.CreateModel(
            name='StgShredSerial',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('batch_id', models.CharField(blank=True, max_length=200)),
                ('batch_date', models.DateField(blank=True, null=True)),
                ('client', models.CharField(blank=True, max_length=200)),
                ('location', models.CharField(blank=True, max_length=200)),
                ('tech', models.CharField(blank=True, max_length=200)),
                ('serial_raw', models.CharField(blank=True, max_length=500)),
                ('serial_norm', models.CharField(blank=True, db_index=True, help_text='Normalized: trim, uppercase, strip trailing punctuation', max_length=500)),
                ('dedupe_key', models.CharField(blank=True, max_length=500)),
                ('event_time', models.DateTimeField(blank=True, null=True)),
                ('is_valid', models.BooleanField(default=True)),
                ('validation_errors', models.JSONField(blank=True, default=list)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('source_event', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='stg_shred', to='ingest.ingestevent')),
            ],
            options={
                'db_table': 'stg_shred_serial',
            },
        ),
        migrations.CreateModel(
            name='StgDriveRemoval',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('client', models.CharField(blank=True, max_length=200)),
                ('computer_serial_raw', models.CharField(blank=True, max_length=500)),
                ('computer_serial_norm', models.CharField(blank=True, max_length=500)),
                ('drive_serial_raw', models.CharField(blank=True, max_length=500)),
                ('drive_serial_norm', models.CharField(blank=True, db_index=True, max_length=500)),
                ('notes', models.TextField(blank=True)),
                ('tech_email', models.EmailField(blank=True, max_length=254)),
                ('event_time', models.DateTimeField(blank=True, null=True)),
                ('is_valid', models.BooleanField(default=True)),
                ('validation_errors', models.JSONField(blank=True, default=list)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('source_event', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='stg_removal', to='ingest.ingestevent')),
            ],
            options={
                'db_table': 'stg_drive_removal',
            },
        ),
        
        # Gold models
        migrations.CreateModel(
            name='Drive',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('serial_norm', models.CharField(db_index=True, max_length=500, unique=True)),
                ('first_seen_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('last_seen_at', models.DateTimeField(default=django.utils.timezone.now)),
            ],
            options={
                'db_table': 'drive',
                'ordering': ['serial_norm'],
            },
        ),
        migrations.CreateModel(
            name='Batch',
            fields=[
                ('batch_id', models.CharField(max_length=200, primary_key=True, serialize=False)),
                ('batch_date', models.DateField(blank=True, null=True)),
                ('client', models.CharField(blank=True, max_length=200)),
                ('location', models.CharField(blank=True, max_length=200)),
                ('tech', models.CharField(blank=True, max_length=200)),
                ('first_seen_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('last_seen_at', models.DateTimeField(default=django.utils.timezone.now)),
            ],
            options={
                'db_table': 'batch',
                'ordering': ['-batch_date'],
            },
        ),
        migrations.CreateModel(
            name='DriveEvent',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('event_type', models.CharField(choices=[('REMOVED', 'Drive Removed'), ('SHREDDED', 'Drive Shredded')], max_length=20)),
                ('event_time', models.DateTimeField()),
                ('client', models.CharField(blank=True, max_length=200)),
                ('computer_serial', models.CharField(blank=True, help_text='For REMOVED events', max_length=500)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('batch', models.ForeignKey(blank=True, help_text='For SHREDDED events', null=True, on_delete=django.db.models.deletion.PROTECT, to='pipeline.batch')),
                ('drive', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='events', to='pipeline.drive')),
                ('source_event', models.ForeignKey(help_text='Provenance back to bronze', on_delete=django.db.models.deletion.PROTECT, to='ingest.ingestevent')),
            ],
            options={
                'db_table': 'drive_event',
                'ordering': ['-event_time'],
            },
        ),
        migrations.CreateModel(
            name='MatchDecision',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('decision', models.CharField(choices=[('MATCH', 'Match'), ('NO_MATCH', 'No Match'), ('AMBIGUOUS', 'Ambiguous')], max_length=20)),
                ('rule_version', models.CharField(default='strict_serial_v1', max_length=100)),
                ('confidence', models.DecimalField(decimal_places=2, help_text='0.0 to 1.0', max_digits=3)),
                ('reason', models.TextField()),
                ('decided_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('drive', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='match_decisions', to='pipeline.drive')),
                ('removed_event', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='match_as_removal', to='pipeline.driveevent')),
                ('shredded_event', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='match_as_shred', to='pipeline.driveevent')),
            ],
            options={
                'db_table': 'match_decision',
                'ordering': ['-decided_at'],
            },
        ),
        
        # Indexes
        migrations.AddIndex(
            model_name='stgshredserial',
            index=models.Index(fields=['serial_norm'], name='stg_shred_s_serial__idx'),
        ),
        migrations.AddIndex(
            model_name='stgshredserial',
            index=models.Index(fields=['batch_id'], name='stg_shred_s_batch_i_idx'),
        ),
        migrations.AddIndex(
            model_name='stgdriveremoval',
            index=models.Index(fields=['drive_serial_norm'], name='stg_drive_r_drive_s_idx'),
        ),
        migrations.AddIndex(
            model_name='driveevent',
            index=models.Index(fields=['event_type', 'event_time'], name='drive_event_event_t_idx'),
        ),
        migrations.AddIndex(
            model_name='matchdecision',
            index=models.Index(fields=['decision'], name='match_decis_decisio_idx'),
        ),
        migrations.AddIndex(
            model_name='matchdecision',
            index=models.Index(fields=['drive', 'decision'], name='match_decis_drive_i_idx'),
        ),
        
        # Constraints
        migrations.AddConstraint(
            model_name='driveevent',
            constraint=models.UniqueConstraint(fields=('source_event', 'event_type'), name='unique_drive_event_per_source'),
        ),
        
        # SQL Views
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE VIEW v_drive_lifecycle AS
            SELECT 
                d.serial_norm,
                MIN(CASE WHEN de.event_type = 'REMOVED' THEN de.event_time END) AS removal_time,
                MIN(CASE WHEN de.event_type = 'SHREDDED' THEN de.event_time END) AS shred_time,
                MAX(CASE WHEN de.event_type = 'SHREDDED' THEN b.batch_id END) AS batch_id,
                MAX(de.client) AS client
            FROM drive d
            LEFT JOIN drive_event de ON de.drive_id = d.id
            LEFT JOIN batch b ON de.batch_id = b.batch_id
            GROUP BY d.serial_norm
            ORDER BY d.serial_norm;
            """,
            reverse_sql="DROP VIEW IF EXISTS v_drive_lifecycle;"
        ),
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE VIEW v_unmatched_removals AS
            SELECT 
                de.id AS event_id,
                d.serial_norm,
                de.event_time AS removal_time,
                de.computer_serial,
                de.client,
                de.notes
            FROM drive_event de
            JOIN drive d ON de.drive_id = d.id
            JOIN match_decision md ON md.drive_id = d.id AND md.removed_event_id = de.id
            WHERE de.event_type = 'REMOVED'
              AND md.decision = 'NO_MATCH'
            ORDER BY de.event_time DESC;
            """,
            reverse_sql="DROP VIEW IF EXISTS v_unmatched_removals;"
        ),
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE VIEW v_unmatched_shreds AS
            SELECT 
                de.id AS event_id,
                d.serial_norm,
                de.event_time AS shred_time,
                b.batch_id,
                de.client
            FROM drive_event de
            JOIN drive d ON de.drive_id = d.id
            LEFT JOIN batch b ON de.batch_id = b.batch_id
            JOIN match_decision md ON md.drive_id = d.id AND md.shredded_event_id = de.id
            WHERE de.event_type = 'SHREDDED'
              AND md.decision = 'NO_MATCH'
            ORDER BY de.event_time DESC;
            """,
            reverse_sql="DROP VIEW IF EXISTS v_unmatched_shreds;"
        ),
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE VIEW v_ambiguous_matches AS
            SELECT 
                md.id AS decision_id,
                d.serial_norm,
                md.confidence,
                md.reason,
                md.decided_at
            FROM match_decision md
            JOIN drive d ON md.drive_id = d.id
            WHERE md.decision = 'AMBIGUOUS'
            ORDER BY md.decided_at DESC;
            """,
            reverse_sql="DROP VIEW IF EXISTS v_ambiguous_matches;"
        ),
    ]
