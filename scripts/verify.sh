#!/bin/bash
set -e

echo "======================================================"
echo "Asset Ledger - Verification Script"
echo "======================================================"

# Navigate to project root
cd "$(dirname "$0")/.."

# Check for required files
echo ""
echo "Checking for required secret files..."
if [ ! -f "secrets/google_sa.json" ]; then
    echo "WARNING: secrets/google_sa.json not found (needed for live sheets pulling)"
    echo "         Tests will run with CSV ingestion only"
fi

if [ ! -f ".env" ]; then
    echo "ERROR: .env file not found"
    echo "Please copy .env.example to .env and configure it"
    exit 1
fi

# Bring down any existing containers
echo ""
echo "Stopping any existing containers..."
docker compose -f docker/compose.yml down -v

# Build and start services
echo ""
echo "Building and starting services..."
docker compose -f docker/compose.yml up -d --build

# Wait for database to be ready
echo ""
echo "Waiting for database to be ready..."
sleep 5

# Run migrations
echo ""
echo "Running migrations..."
docker compose -f docker/compose.yml exec -T web python manage.py migrate

# Run tests
echo ""
echo "Running tests..."
docker compose -f docker/compose.yml exec -T web pytest tests/ -v

# Smoke test: Ingest sample data and run pipeline
echo ""
echo "Running smoke test: Ingest sample data..."
docker compose -f docker/compose.yml exec -T web python manage.py ingest_csv \
    --source=shred_log_serials \
    --file=sample_data/shred_log_serials.csv

docker compose -f docker/compose.yml exec -T web python manage.py ingest_csv \
    --source=drive_removal_log \
    --file=sample_data/drive_removal_log.csv

echo ""
echo "Running pipeline..."
docker compose -f docker/compose.yml exec -T web python manage.py pipeline_run

# Query views
echo ""
echo "Querying views..."
docker compose -f docker/compose.yml exec -T web python manage.py shell <<EOF
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute("SELECT COUNT(*) FROM v_drive_lifecycle")
    print(f"v_drive_lifecycle: {cursor.fetchone()[0]} rows")
    
    cursor.execute("SELECT COUNT(*) FROM v_unmatched_removals")
    print(f"v_unmatched_removals: {cursor.fetchone()[0]} rows")
    
    cursor.execute("SELECT COUNT(*) FROM v_unmatched_shreds")
    print(f"v_unmatched_shreds: {cursor.fetchone()[0]} rows")
    
    cursor.execute("SELECT COUNT(*) FROM v_ambiguous_matches")
    print(f"v_ambiguous_matches: {cursor.fetchone()[0]} rows")
EOF

echo ""
echo "======================================================"
echo "✅ Verification Complete!"
echo "======================================================"
echo ""
echo "Services are running:"
echo "  - Django Admin: http://localhost:8000/admin/"
echo "  - Database: postgres://localhost:5432 (internal only)"
echo ""
echo "To start pgAdmin:"
echo "  docker compose -f docker/compose.yml --profile tools up -d pgadmin"
echo "  Then visit: http://localhost:5050"
echo ""
echo "To view logs:"
echo "  docker compose -f docker/compose.yml logs -f"
echo ""
echo "To stop services:"
echo "  docker compose -f docker/compose.yml down"
echo ""
