#!/bin/bash
set -e

cd "$(dirname "$0")/.."

if [ -z "$1" ]; then
    echo "Usage: $0 <backup_file.sql>"
    echo ""
    echo "Available backups:"
    ls -lh backups/*.sql 2>/dev/null || echo "  No backups found in backups/"
    exit 1
fi

BACKUP_FILE=$1

if [ ! -f "${BACKUP_FILE}" ]; then
    echo "ERROR: Backup file not found: ${BACKUP_FILE}"
    exit 1
fi

# Load environment
source .env

echo "⚠️  WARNING: This will DROP and recreate the database!"
echo "Restoring from: ${BACKUP_FILE}"
read -p "Are you sure? (yes/no): " CONFIRM

if [ "${CONFIRM}" != "yes" ]; then
    echo "Restore cancelled"
    exit 0
fi

echo "Dropping existing database..."
docker compose -f docker/compose.yml exec -T db psql -U ${POSTGRES_USER} -c "DROP DATABASE IF EXISTS ${POSTGRES_DB};"

echo "Creating fresh database..."
docker compose -f docker/compose.yml exec -T db psql -U ${POSTGRES_USER} -c "CREATE DATABASE ${POSTGRES_DB};"

echo "Restoring backup..."
cat ${BACKUP_FILE} | docker compose -f docker/compose.yml exec -T db psql -U ${POSTGRES_USER} -d ${POSTGRES_DB}

echo "✅ Restore complete!"
