# Runbook

Operations guide for Asset Ledger system.

## Initial Setup

### 1. Clone Repository
```bash
git clone <repo-url>
cd asset-ledger
```

### 2. Create Secrets

Create the secrets directory with required credentials:

```bash
# Google Service Account
# 1. Go to Google Cloud Console
# 2. Create a Service Account
# 3. Download JSON key
# 4. Save as secrets/google_sa.json

# pgAdmin password file
# Format: db:5432:*:ledger_user:your_password
echo "db:5432:*:ledger_user:your_secure_password" > secrets/pgpassfile
```

See `secrets/README.md` for detailed instructions.

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

Required variables:
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `DJANGO_SECRET_KEY` (generate with `python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'`)
- `LEDGER_SHEETS_CONFIG` (JSON array of sheet configurations)
- `PGADMIN_DEFAULT_EMAIL`, `PGADMIN_DEFAULT_PASSWORD`

### 4. Share Google Sheets

Share your Google Sheets to the service account email address (found in `google_sa.json` as `client_email`).

### 5. Verify Installation

```bash
./scripts/verify.sh
```

This will:
- Build containers
- Run migrations
- Run all tests
- Execute a smoke test pipeline
- Verify views exist and return data

## Daily Operations

### Starting the System

```bash
cd asset-ledger
docker compose -f docker/compose.yml up -d
```

Services:
- `db`: PostgreSQL database
- `web`: Django web interface (port 8000)
- `scheduler`: Automated pulling and pipeline execution

### Checking Status

```bash
# View all services
docker compose -f docker/compose.yml ps

# View logs
docker compose -f docker/compose.yml logs -f

# View specific service logs
docker compose -f docker/compose.yml logs -f scheduler
```

### Stopping the System

```bash
docker compose -f docker/compose.yml down
```

## Manual Operations

### Manual Pull from Google Sheets

```bash
docker compose -f docker/compose.yml exec web python manage.py pull_sheets
```

### Manual Pipeline Run

```bash
docker compose -f docker/compose.yml exec web python manage.py pipeline_run
```

### Ingest CSV Files (Testing)

```bash
docker compose -f docker/compose.yml exec web python manage.py ingest_csv \
    --source=shred_log_serials \
    --file=sample_data/shred_log_serials.csv
```

### Access Django Admin

1. Create superuser:
   ```bash
   docker compose -f docker/compose.yml exec web python manage.py createsuperuser
   ```

2. Visit http://localhost:8000/admin/

### Access pgAdmin

1. Start pgAdmin:
   ```bash
   docker compose -f docker/compose.yml --profile tools up -d pgadmin
   ```

2. Visit http://localhost:5050

3. Login with credentials from `.env`:
   - Email: `PGADMIN_DEFAULT_EMAIL`
   - Password: `PGADMIN_DEFAULT_PASSWORD`

4. The database server should be pre-registered and auto-login enabled

## Database Operations

### Backup Database

```bash
./scripts/backup_db.sh
```

Backups are stored in `backups/assetledger_YYYYMMDD_HHMMSS.sql`

### Restore Database

```bash
./scripts/restore_db.sh backups/assetledger_20240115_143022.sql
```

⚠️ **Warning**: This will DROP the existing database!

### Direct Database Access

```bash
# Via psql
docker compose -f docker/compose.yml exec db psql -U ledger_user -d assetledger

# Via Django shell
docker compose -f docker/compose.yml exec web python manage.py shell
```

### Reset Database (Fresh Start)

```bash
docker compose -f docker/compose.yml down -v
docker compose -f docker/compose.yml up -d
# Wait for services to start
docker compose -f docker/compose.yml exec web python manage.py migrate
```

## Querying Views

### Using Django Shell

```bash
docker compose -f docker/compose.yml exec web python manage.py shell
```

```python
from django.db import connection

with connection.cursor() as cursor:
    # Drive lifecycle
    cursor.execute("SELECT * FROM v_drive_lifecycle LIMIT 10")
    for row in cursor.fetchall():
        print(row)
    
    # Unmatched removals
    cursor.execute("SELECT serial_norm, removal_time FROM v_unmatched_removals")
    for row in cursor.fetchall():
        print(f"Unmatched removal: {row[0]} at {row[1]}")
```

### Using psql

```bash
docker compose -f docker/compose.yml exec db psql -U ledger_user -d assetledger
```

```sql
-- All drives with their lifecycle
SELECT * FROM v_drive_lifecycle;

-- Drives removed but not shredded
SELECT * FROM v_unmatched_removals;

-- Drives shredded but no removal record
SELECT * FROM v_unmatched_shreds;

-- Ambiguous matches
SELECT * FROM v_ambiguous_matches;
```

## Monitoring

### Check Scheduler is Running

```bash
# Should see periodic log entries
docker compose -f docker/compose.yml logs -f scheduler
```

Expected output every 15 minutes (default):
```
[TIMESTAMP] Running pull_sheets...
[TIMESTAMP] Running pipeline_run...
[TIMESTAMP] Sleeping for 900 seconds...
```

### Check for Errors

```bash
# Look for Python exceptions or errors
docker compose -f docker/compose.yml logs scheduler | grep -i error

# Check validation errors in staging
docker compose -f docker/compose.yml exec web python manage.py shell
```

```python
from pipeline.models import StgShredSerial, StgDriveRemoval

# Invalid shreds
invalid_shreds = StgShredSerial.objects.filter(is_valid=False)
for s in invalid_shreds:
    print(f"{s.serial_raw}: {s.validation_errors}")

# Invalid removals
invalid_removals = StgDriveRemoval.objects.filter(is_valid=False)
for r in invalid_removals:
    print(f"{r.drive_serial_raw}: {r.validation_errors}")
```

## Troubleshooting

### Services won't start

1. Check Docker is running: `docker ps`
2. Check .env file exists and is valid
3. Check logs: `docker compose -f docker/compose.yml logs`

### Database connection errors

1. Verify `DATABASE_URL` in .env matches `POSTGRES_*` variables
2. Check db container is healthy: `docker compose -f docker/compose.yml ps`
3. Check network: `docker network ls`

### Google Sheets pull fails

1. Verify `secrets/google_sa.json` exists and is valid JSON
2. Verify sheets are shared to service account email
3. Check service account has appropriate permissions
4. Check logs: `docker compose -f docker/compose.yml logs scheduler`

### No data in views

1. Verify data was ingested: `SELECT COUNT(*) FROM ingest_event;`
2. Run pipeline manually: `docker compose -f docker/compose.yml exec web python manage.py pipeline_run`
3. Check for staging errors: See "Check for Errors" section above

### pgAdmin server not registered

1. Verify `secrets/pgpassfile` exists and format matches:
   ```
   db:5432:*:ledger_user:your_password
   ```
2. Verify password matches `.env` file
3. Restart pgAdmin: `docker compose -f docker/compose.yml --profile tools restart pgadmin`

## Scheduled Maintenance

### Weekly
- Review validation errors
- Check disk space (`df -h`)
- Review unmatched drives

### Monthly
- Backup database
- Review and archive old backups
- Check for Django/Python security updates

### Quarterly
- Review and optimize database indexes
- Review matching rules for improvements
- Update documentation if workflows change
