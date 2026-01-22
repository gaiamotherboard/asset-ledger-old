# Deployment Guide

## Quick Start (30 seconds)

```bash
# 1. Extract the project
tar xzf asset-ledger.tar.gz
cd asset-ledger

# 2. Configure credentials (edit with your values)
nano .env
# Update: POSTGRES_PASSWORD, DJANGO_SECRET_KEY, LEDGER_SHEETS_CONFIG, PGADMIN_*

# 3. Add Google Service Account JSON
# Place your service account key at: secrets/google_sa.json

# 4. Create pgAdmin password file
echo "db:5432:*:ledger_user:YOUR_POSTGRES_PASSWORD" > secrets/pgpassfile

# 5. Verify everything works
./scripts/verify.sh
```

That's it! The system is now running.

## What Just Happened?

The `verify.sh` script:
1. ✅ Built all Docker containers
2. ✅ Started PostgreSQL, Django, and the scheduler
3. ✅ Ran database migrations
4. ✅ Executed all tests (Bronze, Silver, Gold, Matching, Views)
5. ✅ Ran a smoke test with sample data
6. ✅ Verified all SQL views work

## Services Running

- **Django Web/Admin**: http://localhost:8000/admin/
  - Create superuser: `docker compose -f docker/compose.yml exec web python manage.py createsuperuser`

- **Scheduler**: Automatically pulls from Google Sheets every 15 minutes
  - View logs: `docker compose -f docker/compose.yml logs -f scheduler`

- **pgAdmin** (optional): http://localhost:5050
  - Start: `docker compose -f docker/compose.yml --profile tools up -d pgadmin`
  - Login with credentials from `.env`
  - Database server pre-registered and auto-connected

## Google Sheets Setup

1. **Create Service Account** in Google Cloud Console
2. **Download JSON key** → save as `secrets/google_sa.json`
3. **Share your spreadsheets** to the service account email (found in the JSON as `client_email`)
4. **Configure sheet IDs** in `.env` under `LEDGER_SHEETS_CONFIG`

Example configuration:
```json
[
  {
    "name": "shred_log_serials",
    "sheet_id": "1ABC...XYZ",
    "tab": "Form Responses 1",
    "header_row": 1
  },
  {
    "name": "drive_removal_log", 
    "sheet_id": "1DEF...UVW",
    "tab": "Form Responses 1",
    "header_row": 1
  }
]
```

## Daily Operations

### Check System Status
```bash
docker compose -f docker/compose.yml ps
docker compose -f docker/compose.yml logs -f
```

### Manual Operations
```bash
# Pull from Google Sheets now
docker compose -f docker/compose.yml exec web python manage.py pull_sheets

# Run pipeline now
docker compose -f docker/compose.yml exec web python manage.py pipeline_run

# Access Django shell
docker compose -f docker/compose.yml exec web python manage.py shell
```

### Query Reports
```bash
docker compose -f docker/compose.yml exec web python manage.py shell
```

```python
from django.db import connection

with connection.cursor() as cursor:
    # Drives removed but not shredded
    cursor.execute("SELECT * FROM v_unmatched_removals")
    for row in cursor.fetchall():
        print(row)
    
    # Drives shredded but no removal record
    cursor.execute("SELECT * FROM v_unmatched_shreds")
    for row in cursor.fetchall():
        print(row)
```

### Backup Database
```bash
./scripts/backup_db.sh
# Creates: backups/assetledger_YYYYMMDD_HHMMSS.sql
```

### Restore Database
```bash
./scripts/restore_db.sh backups/assetledger_20240115_120000.sql
```

## Troubleshooting

### "Services won't start"
- Check Docker is running: `docker ps`
- Check `.env` file exists and has valid values
- View logs: `docker compose -f docker/compose.yml logs`

### "Google Sheets pull fails"
- Verify `secrets/google_sa.json` exists and is valid JSON
- Verify sheets are shared to the service account email
- Check scheduler logs: `docker compose -f docker/compose.yml logs scheduler`

### "pgAdmin won't connect"
- Verify `secrets/pgpassfile` format: `db:5432:*:ledger_user:password`
- Verify password matches `.env` file
- Restart pgAdmin: `docker compose -f docker/compose.yml --profile tools restart pgadmin`

## Architecture Summary

```
Google Sheets (Staff UI)
       ↓
[Scheduler pulls every 15 min]
       ↓
Bronze Layer (Append-only raw data)
       ↓
Silver Layer (Normalized + validated)
       ↓
Gold Layer (Canonical entities)
       ↓
Match Decisions (Explicit matching)
       ↓
SQL Views (Reports)
```

### Key Features

- ✅ **Pull-only**: No public exposure required
- ✅ **Idempotent**: Safe to re-pull same data
- ✅ **Append-only Bronze**: Immutable audit trail
- ✅ **Validation**: Flags errors without crashing
- ✅ **Explicit Matching**: Every drive gets a MATCH/NO_MATCH/AMBIGUOUS decision
- ✅ **Deterministic**: Full test coverage

## Next Steps

1. **Share Google Sheets** to service account email
2. **Create Django superuser** for admin access
3. **Review first pull** in scheduler logs
4. **Check reports** in SQL views or pgAdmin
5. **Schedule backups** (recommended: daily)

## Support

For detailed operations, see:
- [RUNBOOK.md](docs/RUNBOOK.md) - Complete operations guide
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - System design
- [PRD.md](docs/PRD.md) - Requirements and acceptance criteria

## Files You Need

Required (create before first run):
- `.env` - Configuration (copy from `.env.example`)
- `secrets/google_sa.json` - Google Service Account credentials
- `secrets/pgpassfile` - pgAdmin auto-login file

The system will NOT start without these files.
