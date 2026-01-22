# Implementation Verification Checklist

## ✅ Stage 0: Infrastructure

- [x] Docker Compose stack (`docker/compose.yml`) created
- [x] Services: db (Postgres 16), web (Django+gunicorn), scheduler, pgAdmin
- [x] Postgres NOT exposed to host/LAN (internal network only)
- [x] Web exposed on 0.0.0.0:8000
- [x] pgAdmin bound to 127.0.0.1:5050 (localhost only)
- [x] Scheduler loops every PULL_INTERVAL_SECONDS
- [x] All services use `restart: unless-stopped`
- [x] Healthcheck on db service
- [x] `.gitignore` excludes secrets/, .env
- [x] `.env.example` created with all required variables

## ✅ Stage 1: Bronze Layer (Append-Only)

- [x] `IngestEvent` model with UUID PK
- [x] Fields: source_system, source_sheet_id, source_tab, source_row_key
- [x] Fields: payload (JSONField), payload_hash, schema_version
- [x] Fields: source_timestamp, ingested_at
- [x] Unique constraint on (source_system, source_sheet_id, source_tab, source_row_key, payload_hash)
- [x] `compute_payload_hash()` static method
- [x] `pull_sheets` management command
- [x] Reads LEDGER_SHEETS_CONFIG from environment
- [x] Uses Google Sheets API with service account
- [x] Logs inserted vs duplicate counts
- [x] `ingest_csv` management command for testing

## ✅ Stage 2: Silver Layer (Normalized Staging)

- [x] `StgShredSerial` model with OneToOne FK to IngestEvent
- [x] Fields: batch_id, batch_date, client, location, tech
- [x] Fields: serial_raw, serial_norm, dedupe_key, event_time
- [x] Fields: is_valid, validation_errors (JSONField)
- [x] `StgDriveRemoval` model with OneToOne FK to IngestEvent
- [x] Fields: client, computer_serial_raw, computer_serial_norm
- [x] Fields: drive_serial_raw, drive_serial_norm, notes, tech_email
- [x] Fields: event_time, is_valid, validation_errors
- [x] `normalize_serial()` function: trim → uppercase → strip trailing punctuation
- [x] `validate_shred_row()` function
- [x] `validate_removal_row()` function (flags URLs in computer serial)
- [x] `stage_all_new()` in stage.py
- [x] `pipeline_run` command stages new events

## ✅ Stage 3: Gold Layer (Canonical Entities)

- [x] `Drive` model with unique serial_norm
- [x] Fields: first_seen_at, last_seen_at
- [x] `Batch` model with PK batch_id
- [x] Fields: batch_date, client, location, tech, first_seen_at, last_seen_at
- [x] `DriveEvent` model with FK to Drive
- [x] EVENT_TYPE_CHOICES: REMOVED, SHREDDED
- [x] Fields: event_time, source_event (FK to IngestEvent)
- [x] Fields: batch (nullable, for SHREDDED), client, computer_serial, notes
- [x] Unique constraint on (source_event, event_type)
- [x] `promote_all_valid()` in promote.py
- [x] Upsert pattern for Drive and Batch
- [x] `pipeline_run` promotes valid staging to Gold

## ✅ Stage 4: Matching as Product

- [x] `MatchDecision` model with FK to Drive
- [x] DECISION_CHOICES: MATCH, NO_MATCH, AMBIGUOUS
- [x] Fields: removed_event (FK nullable), shredded_event (FK nullable)
- [x] Fields: rule_version, confidence (Decimal 0.0-1.0), reason
- [x] Fields: decided_at
- [x] `run_matching()` in match.py
- [x] `apply_strict_matching_v1()` logic:
  - [x] 1 removal + 1 shred = MATCH (confidence 1.0)
  - [x] Only removal = NO_MATCH (confidence 0.0)
  - [x] Only shred = NO_MATCH (confidence 0.0)
  - [x] Multiple candidates = AMBIGUOUS (confidence 0.5)
- [x] `pipeline_run` creates match decisions
- [x] Every drive gets a decision

## ✅ Stage 5: Reporting Views

- [x] `v_drive_lifecycle` view created via migration
- [x] `v_unmatched_removals` view created
- [x] `v_unmatched_shreds` view created
- [x] `v_ambiguous_matches` view created
- [x] Views use RunSQL in migration
- [x] Views queryable via Django shell

## ✅ Stage 6: pgAdmin Pre-Registration

- [x] `docker/pgadmin/servers.json` created and committed
- [x] Server config points to db:5432
- [x] Uses /pgpassfile for password
- [x] `secrets/pgpassfile` format documented
- [x] pgAdmin environment variables configured
- [x] Server appears in tree on first login

## ✅ Stage 7: Sample Data & Tests

- [x] `sample_data/shred_log_serials.csv` created with:
  - [x] Strict match case (ABC123XYZ, DEF456UVW, Z9919D52)
  - [x] Unmatched removal (ORPHAN999)
  - [x] Unmatched shred (ORPHAN123)
  - [x] Serial with trailing punctuation (Z9919D52.)
  - [x] Computer serial as URL (www.example.com)
- [x] `sample_data/drive_removal_log.csv` created
- [x] `tests/test_bronze_idempotency.py` created
- [x] `tests/test_stage_silver.py` created
- [x] `tests/test_promote_gold.py` created
- [x] `tests/test_matching_outputs.py` created
- [x] `tests/test_views_exist.py` created
- [x] pytest.ini configured

## ✅ Stage 8: Scripts & Verification

- [x] `scripts/verify.sh` created and executable
- [x] Brings up stack, runs migrations, runs tests
- [x] Ingests sample data and runs pipeline
- [x] Queries all views for smoke test
- [x] Exits non-zero on failure
- [x] `scripts/backup_db.sh` created
- [x] `scripts/restore_db.sh` created

## ✅ Stage 9: Documentation

- [x] `README.md` with quick start
- [x] `DEPLOYMENT.md` with 30-second setup guide
- [x] `docs/ARCHITECTURE.md` with design principles
- [x] `docs/RUNBOOK.md` with operations guide
- [x] `docs/PRD.md` with acceptance criteria
- [x] `docs/PROMPTS/claude_build.md` with build spec
- [x] `secrets/README.md` with credential instructions

## ✅ Additional Quality Checks

- [x] All Python files have proper imports
- [x] Django settings configured correctly
- [x] manage.py executable
- [x] All __init__.py files created
- [x] Migrations created for ingest and pipeline apps
- [x] Admin.py registered all models
- [x] Docker builds successfully
- [x] No secrets committed to repo
- [x] Sample data is sanitized

## Done Condition Met

ALL of the following are TRUE:

✅ **Infrastructure**: Docker Compose stack with all 4 services  
✅ **Bronze**: Append-only IngestEvent with idempotency  
✅ **Silver**: Staging with normalization and validation  
✅ **Gold**: Canonical entities with upsert pattern  
✅ **Matching**: Explicit decisions for all drives  
✅ **Views**: 4 SQL views created and queryable  
✅ **pgAdmin**: Pre-registered server with auto-login  
✅ **Sample Data**: Covers all test cases  
✅ **Tests**: Comprehensive test suite (5 test files)  
✅ **Scripts**: verify.sh, backup_db.sh, restore_db.sh  
✅ **Docs**: Complete documentation (6 files)  

## Final Verification Command

```bash
cd asset-ledger
./scripts/verify.sh
```

Expected result: **EXIT 0** with all tests passing and views populated.

## Deliverables

The complete system is packaged in: **asset-ledger.tar.gz**

Extract and run `./scripts/verify.sh` to verify everything works!
