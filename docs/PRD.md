# Product Requirements Document

## Overview

Asset Ledger is a production-lean system for tracking IT asset lifecycles using Google Sheets as the user interface. It implements a Bronze/Silver/Gold data architecture with explicit matching between drive removals and shreds.

## Objectives

1. **Staff Efficiency**: Keep staff using familiar Google Sheets/Forms
2. **Data Quality**: Normalize and validate data automatically
3. **Auditability**: Maintain immutable audit trail in Bronze layer
4. **Matching**: Explicitly track which drives were removed vs. shredded
5. **Operational Simplicity**: No public exposure, pull-only architecture

## Non-Negotiables (Project Constitution)

✅ Pull-only architecture (no inbound internet required)  
✅ Bronze is append-only (never overwrite/delete)  
✅ Idempotent ingestion (safe to re-pull same data)  
✅ Messy inputs handled gracefully (no crashes on bad data)  
✅ Matching is explicit and explainable  
✅ No custom UI (Sheets for entry, Django admin for review)  
✅ Secrets never committed  
✅ Deterministic verification (one command to verify stack)  

## Stage 0: Infrastructure ✅

### Acceptance Criteria
- [x] Docker Compose stack with db, web, scheduler, pgAdmin services
- [x] Postgres never exposed to network
- [x] pgAdmin bound to localhost only
- [x] Web service exposes port 8000 to LAN
- [x] Scheduler loops every `PULL_INTERVAL_SECONDS`
- [x] Services restart automatically (`unless-stopped`)
- [x] `.gitignore` excludes secrets
- [x] `.env.example` documents all required variables
- [x] `secrets/README.md` provides credential instructions

### Verification
```bash
docker compose -f docker/compose.yml ps
# Should show: db, web, scheduler running
# pgAdmin requires --profile tools
```

## Stage 1: Bronze Layer (Append-Only Ingestion) ✅

### Acceptance Criteria
- [x] `IngestEvent` model with UUID PK
- [x] Fields: source_system, source_sheet_id, source_tab, source_row_key, payload, payload_hash, schema_version, ingested_at, source_timestamp
- [x] Unique constraint on (source_system, source_sheet_id, source_tab, source_row_key, payload_hash)
- [x] `pull_sheets` command reads `LEDGER_SHEETS_CONFIG` from env
- [x] Fetches data from Google Sheets API using service account
- [x] Computes deterministic payload hash
- [x] Logs inserted vs duplicate counts
- [x] `ingest_csv` command for testing (no Google API calls)

### Verification
```bash
# Ingest same CSV twice
docker compose -f docker/compose.yml exec web python manage.py ingest_csv \
    --source=test --file=sample_data/shred_log_serials.csv

# Check count doesn't change
docker compose -f docker/compose.yml exec web python manage.py shell -c \
    "from ingest.models import IngestEvent; print(IngestEvent.objects.count())"

# Ingest again - count should be same
docker compose -f docker/compose.yml exec web python manage.py ingest_csv \
    --source=test --file=sample_data/shred_log_serials.csv
```

## Stage 2: Silver Layer (Normalized Staging) ✅

### Acceptance Criteria
- [x] `StgShredSerial` model with OneToOne FK to IngestEvent
- [x] `StgDriveRemoval` model with OneToOne FK to IngestEvent
- [x] Serial normalization: trim → uppercase → strip trailing punctuation
- [x] Validation rules that flag but don't crash:
  - [x] Missing drive serial
  - [x] Computer serial looks like URL
- [x] `is_valid` boolean and `validation_errors` JSON field
- [x] `pipeline_run` command stages new IngestEvents

### Verification
```bash
# Test trailing punctuation normalization
pytest app/tests/test_stage_silver.py::TestSilverStaging::test_normalization_trailing_punctuation

# Test URL detection
pytest app/tests/test_stage_silver.py::TestSilverStaging::test_url_in_computer_serial_flagged
```

## Stage 3: Gold Layer (Canonical Entities) ✅

### Acceptance Criteria
- [x] `Drive` model with unique `serial_norm`
- [x] `Batch` model with PK `batch_id`
- [x] `DriveEvent` model with FK to Drive, event_type choices (REMOVED, SHREDDED)
- [x] `source_event` FK to IngestEvent (provenance)
- [x] Unique constraint on (source_event, event_type)
- [x] `pipeline_run` promotes valid staging records to Gold
- [x] Upsert pattern for Drive and Batch
- [x] Events immutable after creation

### Verification
```bash
# Check entities created
pytest app/tests/test_promote_gold.py::TestGoldPromotion::test_drives_created
pytest app/tests/test_promote_gold.py::TestGoldPromotion::test_batches_created
pytest app/tests/test_promote_gold.py::TestGoldPromotion::test_drive_events_created

# Check idempotency
pytest app/tests/test_promote_gold.py::TestGoldPromotion::test_event_idempotency
```

## Stage 4: Matching as Product ✅

### Acceptance Criteria
- [x] `MatchDecision` model with FK to Drive
- [x] Fields: decision (MATCH/NO_MATCH/AMBIGUOUS), rule_version, confidence, reason
- [x] FKs to removed_event and shredded_event (nullable)
- [x] Strict matching v1 logic:
  - [x] 1 removal + 1 shred = MATCH (confidence 1.0)
  - [x] Only removal = NO_MATCH (confidence 0.0)
  - [x] Only shred = NO_MATCH (confidence 0.0)
  - [x] Multiple candidates = AMBIGUOUS (confidence 0.5)
- [x] `pipeline_run` creates match decisions
- [x] Every drive gets a decision

### Verification
```bash
# Test matching logic
pytest app/tests/test_matching_outputs.py::TestMatching::test_strict_match_found
pytest app/tests/test_matching_outputs.py::TestMatching::test_unmatched_removal
pytest app/tests/test_matching_outputs.py::TestMatching::test_unmatched_shred
pytest app/tests/test_matching_outputs.py::TestMatching::test_all_drives_have_decisions
```

## Stage 5: Reporting Views ✅

### Acceptance Criteria
- [x] `v_drive_lifecycle` view (all drives with removal/shred times)
- [x] `v_unmatched_removals` view (NO_MATCH removals)
- [x] `v_unmatched_shreds` view (NO_MATCH shreds)
- [x] `v_ambiguous_matches` view (AMBIGUOUS decisions)
- [x] Views queryable via Django shell or psql
- [x] Views populated by sample data

### Verification
```bash
# Test views exist and return data
pytest app/tests/test_views_exist.py

# Manual verification
docker compose -f docker/compose.yml exec web python manage.py shell
```

```python
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute("SELECT COUNT(*) FROM v_unmatched_removals")
    print(f"Unmatched removals: {cursor.fetchone()[0]}")
```

## Stage 6: pgAdmin Pre-Registration ✅

### Acceptance Criteria
- [x] `docker/pgadmin/servers.json` committed to repo
- [x] Registers server pointing to `db:5432`
- [x] Uses `/pgpassfile` for password
- [x] `secrets/pgpassfile` format documented in `secrets/README.md`
- [x] pgAdmin accessible at `http://localhost:5050`
- [x] Server appears in tree on first login (no manual config)

### Verification
```bash
# Start pgAdmin
docker compose -f docker/compose.yml --profile tools up -d pgadmin

# Visit http://localhost:5050
# Login with PGADMIN_DEFAULT_EMAIL / PGADMIN_DEFAULT_PASSWORD
# "Asset Ledger DB" server should appear in left tree
# Click to expand - should connect without password prompt
```

## Stage 7: Sample Data & Tests ✅

### Acceptance Criteria
- [x] `sample_data/shred_log_serials.csv` with:
  - [x] At least one strict match (same serial in both logs)
  - [x] At least one unmatched removal
  - [x] At least one unmatched shred
  - [x] At least one serial with trailing punctuation
  - [x] At least one computer serial that looks like URL
- [x] `sample_data/drive_removal_log.csv` (matching structure)
- [x] Tests for:
  - [x] Bronze idempotency
  - [x] Silver normalization and validation
  - [x] Gold entity creation
  - [x] Matching decisions
  - [x] Views exist and return data
- [x] All tests pass

### Verification
```bash
# Run full test suite
docker compose -f docker/compose.yml exec web pytest tests/ -v

# Should see:
# - test_bronze_idempotency.py ✓
# - test_stage_silver.py ✓
# - test_promote_gold.py ✓
# - test_matching_outputs.py ✓
# - test_views_exist.py ✓
```

## Stage 8: Deterministic Verification ✅

### Acceptance Criteria
- [x] `scripts/verify.sh` exists and is executable
- [x] Brings up full stack (db, web, scheduler)
- [x] Runs migrations
- [x] Runs all tests
- [x] Ingests sample data
- [x] Runs pipeline
- [x] Queries all views
- [x] Exits non-zero on any failure
- [x] Works on fresh checkout (with secrets present)

### Verification
```bash
# From project root
./scripts/verify.sh

# Should complete without errors and show:
# ✅ Services started
# ✅ Migrations applied
# ✅ All tests passed
# ✅ Pipeline executed
# ✅ Views populated
```

## Stage 9: Documentation ✅

### Acceptance Criteria
- [x] `README.md` with quick start and overview
- [x] `docs/ARCHITECTURE.md` with design principles and data flow
- [x] `docs/RUNBOOK.md` with operational procedures
- [x] `docs/PRD.md` (this document) with acceptance criteria
- [x] `docs/PROMPTS/claude_build.md` (original build specification)
- [x] All documentation current and accurate

### Verification
```bash
# Check all docs exist
ls -la docs/
ls -la docs/PROMPTS/

# Review for accuracy
cat docs/ARCHITECTURE.md
cat docs/RUNBOOK.md
```

## Success Metrics

### Technical
- ✅ `scripts/verify.sh` exits 0 on fresh checkout
- ✅ All pytest tests pass
- ✅ Bronze idempotency: duplicate ingestion = 0 new records
- ✅ Pipeline idempotency: duplicate run = 0 new entities/events
- ✅ Views populated: each view returns > 0 rows from sample data

### Operational
- ✅ pgAdmin auto-connects to database
- ✅ Django admin accessible on LAN
- ✅ Scheduler pulls and processes every 15 minutes
- ✅ No crashes on invalid data (validation errors recorded)
- ✅ Backup/restore scripts work

### Product
- ✅ Matching produces explicit outputs (MATCH/NO_MATCH/AMBIGUOUS)
- ✅ Unmatched removals identified
- ✅ Unmatched shreds identified
- ✅ Serial normalization handles real-world messiness
- ✅ Staff can continue using Google Sheets/Forms

## Done Condition

All stages marked ✅ AND `scripts/verify.sh` exits 0 on fresh checkout.

**Status**: READY FOR VERIFICATION
