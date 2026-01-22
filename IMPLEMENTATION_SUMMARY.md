# Asset Ledger - Implementation Complete

## What Was Built

A production-lean Django+Postgres system for IT asset tracking that:

✅ Uses Google Sheets as the UI (staff keep using familiar tools)  
✅ Pulls data on a schedule (no public exposure required)  
✅ Implements Bronze/Silver/Gold data architecture  
✅ Provides explicit matching between drive removals and shreds  
✅ Includes pre-configured pgAdmin with auto-login  
✅ Is fully tested and deterministically verifiable  

## Key Features

### Data Architecture
- **Bronze Layer**: Append-only immutable audit trail
- **Silver Layer**: Normalized staging with validation
- **Gold Layer**: Canonical entities and events
- **Matching**: First-class product with explicit decisions

### Matching Logic
Every drive gets one of three decisions:
- **MATCH** (confidence 1.0): Exactly 1 removal + 1 shred
- **NO_MATCH** (confidence 0.0): Only removal OR only shred
- **AMBIGUOUS** (confidence 0.5): Multiple candidates

### Data Quality
- **Serial Normalization**: Handles trailing punctuation, case differences
- **Validation**: Flags issues (like URLs in wrong fields) without crashing
- **Idempotency**: Safe to re-pull same data repeatedly

### Operations
- **Pull-Only**: No inbound connections required
- **Automated**: Scheduler pulls every 15 minutes
- **Pre-configured**: pgAdmin server auto-registered
- **Backed Up**: Scripts for backup/restore included

## Project Structure

```
asset-ledger/
├── app/                          # Django application
│   ├── assetledger/             # Project settings
│   ├── ingest/                  # Bronze layer (append-only)
│   │   ├── models.py            # IngestEvent
│   │   ├── admin.py
│   │   └── management/commands/
│   │       ├── pull_sheets.py   # Google Sheets puller
│   │       └── ingest_csv.py    # CSV ingestion for testing
│   ├── pipeline/                # Silver/Gold layers + matching
│   │   ├── models.py            # Staging + canonical entities
│   │   ├── normalize.py         # Serial normalization
│   │   ├── stage.py             # Bronze → Silver
│   │   ├── promote.py           # Silver → Gold
│   │   ├── match.py             # Matching logic
│   │   └── management/commands/
│   │       └── pipeline_run.py  # Full pipeline execution
│   ├── tests/                   # Comprehensive test suite
│   │   ├── test_bronze_idempotency.py
│   │   ├── test_stage_silver.py
│   │   ├── test_promote_gold.py
│   │   ├── test_matching_outputs.py
│   │   └── test_views_exist.py
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── manage.py
├── docker/
│   ├── compose.yml              # Docker Compose stack
│   └── pgadmin/
│       └── servers.json         # Pre-registered server
├── scripts/
│   ├── verify.sh                # Full verification script
│   ├── backup_db.sh
│   └── restore_db.sh
├── sample_data/
│   ├── shred_log_serials.csv
│   └── drive_removal_log.csv
├── docs/
│   ├── ARCHITECTURE.md
│   ├── RUNBOOK.md
│   ├── PRD.md
│   └── PROMPTS/
│       └── claude_build.md
├── secrets/                     # gitignored
│   ├── README.md
│   ├── google_sa.json           # Google Service Account (you provide)
│   └── pgpassfile               # pgAdmin auto-login (you create)
├── README.md
├── DEPLOYMENT.md
├── VERIFICATION_CHECKLIST.md
├── .env                         # Configuration (you edit)
├── .env.example
└── .gitignore
```

## Database Schema

### Bronze
- `ingest_event` - Raw data from Google Sheets

### Silver
- `stg_shred_serial` - Normalized shred log entries
- `stg_drive_removal` - Normalized drive removal entries

### Gold
- `drive` - Canonical drive entities (by normalized serial)
- `batch` - Shred batch entities
- `drive_event` - Lifecycle events (REMOVED, SHREDDED)
- `match_decision` - Matching decisions with confidence scores

### Views (Reporting Surface)
- `v_drive_lifecycle` - Complete lifecycle per drive
- `v_unmatched_removals` - Drives removed but not shredded
- `v_unmatched_shreds` - Drives shredded but no removal record
- `v_ambiguous_matches` - Drives with unclear matching

## Test Coverage

**5 test modules** with comprehensive coverage:

1. **Bronze Idempotency**: Duplicate ingestion prevention
2. **Silver Staging**: Normalization and validation
3. **Gold Promotion**: Entity creation and upserts
4. **Matching Logic**: All decision types (MATCH/NO_MATCH/AMBIGUOUS)
5. **Views**: SQL views exist and return correct data

**Sample data** exercises all edge cases:
- Strict matches (same serial in both logs)
- Unmatched removals (drive removed but never shredded)
- Unmatched shreds (drive shredded but no removal record)
- Serial normalization (trailing punctuation)
- Validation (URL in computer serial field)

## Deployment (30 seconds)

```bash
# 1. Extract
tar xzf asset-ledger.tar.gz && cd asset-ledger

# 2. Configure
nano .env  # Update passwords, sheet IDs
# Add: secrets/google_sa.json (your service account key)
# Add: secrets/pgpassfile (db:5432:*:user:password)

# 3. Verify
./scripts/verify.sh
```

That's it! Services are running and verified.

## Accessing the System

- **Django Admin**: http://localhost:8000/admin/
  - First create superuser: `docker compose -f docker/compose.yml exec web python manage.py createsuperuser`

- **pgAdmin**: http://localhost:5050 (optional)
  - Start: `docker compose -f docker/compose.yml --profile tools up -d pgadmin`
  - Server pre-registered, auto-login enabled

- **Database**: Not exposed (internal Docker network only)
  - Access via Django shell or pgAdmin

## Google Sheets Setup

1. Create Service Account in Google Cloud Console
2. Download JSON key → save as `secrets/google_sa.json`
3. Share your spreadsheets to the service account email
4. Configure sheet IDs in `.env` under `LEDGER_SHEETS_CONFIG`

## Operational Commands

```bash
# View logs
docker compose -f docker/compose.yml logs -f scheduler

# Manual pull from Google Sheets
docker compose -f docker/compose.yml exec web python manage.py pull_sheets

# Manual pipeline run
docker compose -f docker/compose.yml exec web python manage.py pipeline_run

# Backup database
./scripts/backup_db.sh

# Restore database
./scripts/restore_db.sh backups/assetledger_20240115_120000.sql

# Query reports
docker compose -f docker/compose.yml exec web python manage.py shell
```

```python
# In Django shell
from django.db import connection
with connection.cursor() as c:
    c.execute("SELECT * FROM v_unmatched_removals")
    for row in c.fetchall():
        print(row)
```

## Architecture Highlights

### Pull-Only Design
- NUC not publicly exposed
- No inbound connections required
- Scheduler polls Google Sheets (default: every 15 minutes)

### Idempotency Everywhere
- Bronze: Unique constraint on (source, sheet, tab, row, hash)
- Silver: OneToOne FK to Bronze
- Gold: Unique constraints on (source_event, event_type)
- Matching: One decision per drive per rule version

### Explainable Matching
- Every decision has a `reason` field
- `rule_version` enables algorithm evolution
- Confidence scores (0.0 to 1.0)

### No Custom UI
- Staff use Google Sheets/Forms (familiar tools)
- Django admin for internal review (LAN access)
- SQL views for reporting

## Documentation

- **DEPLOYMENT.md** - Quick start guide
- **README.md** - Project overview
- **docs/ARCHITECTURE.md** - Design principles and data flow
- **docs/RUNBOOK.md** - Operations guide
- **docs/PRD.md** - Requirements and acceptance criteria
- **VERIFICATION_CHECKLIST.md** - Complete implementation checklist

## Verification

The system is **deterministically verifiable** in one command:

```bash
./scripts/verify.sh
```

This script:
1. Builds and starts all services
2. Runs database migrations
3. Executes full test suite
4. Ingests sample data
5. Runs complete pipeline
6. Queries all SQL views
7. Exits 0 if all checks pass

## Success Criteria (All Met ✅)

✅ Pull-only architecture  
✅ Bronze append-only  
✅ Idempotent ingestion  
✅ Handles messy inputs gracefully  
✅ Explicit matching with NO_MATCH outputs  
✅ No custom UI  
✅ Secrets gitignored  
✅ Deterministic verification  
✅ pgAdmin pre-registered  
✅ Tests pass  
✅ Views populated  

## Next Steps

1. **Deploy** to your NUC
2. **Configure** Google Service Account
3. **Share** spreadsheets to service account
4. **Run** `./scripts/verify.sh`
5. **Monitor** scheduler logs
6. **Review** reports in SQL views

## Support

See documentation in `docs/` directory:
- Operations questions → RUNBOOK.md
- Architecture questions → ARCHITECTURE.md
- Requirements → PRD.md

---

**Status**: Implementation complete. All acceptance criteria met. Ready for deployment.

**Deliverable**: asset-ledger.tar.gz (30KB)
