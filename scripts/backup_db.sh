#!/bin/bash
set -e

cd "$(dirname "$0")/.."

# Load environment
source .env

BACKUP_DIR="backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/assetledger_${TIMESTAMP}.sql"

mkdir -p ${BACKUP_DIR}

echo "Backing up database to ${BACKUP_FILE}..."

docker compose -f docker/compose.yml exec -T db pg_dump \
    -U ${POSTGRES_USER} \
    -d ${POSTGRES_DB} \
    > ${BACKUP_FILE}

echo "✅ Backup complete: ${BACKUP_FILE}"
echo "Size: $(du -h ${BACKUP_FILE} | cut -f1)"
