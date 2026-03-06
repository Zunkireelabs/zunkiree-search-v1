#!/bin/sh
# Zunkiree Search — Per-tenant backup snapshot
# Runs inside postgres:16-alpine container

set -e

BACKUP_DIR="/backups"
TIMESTAMP=$(date -u +%Y%m%d_%H%M%S)
DB_URL="$DATABASE_URL"
TABLES="customers user_profiles query_logs verification_sessions widget_configs domains document_chunks ingestion_jobs"

if [ -z "$DB_URL" ]; then
  echo "ERROR: DATABASE_URL not set"
  exit 1
fi

mkdir -p "$BACKUP_DIR"

# Full snapshot (all tenant data, compressed)
OUTFILE="${BACKUP_DIR}/zunkiree_full_${TIMESTAMP}.sql.gz"
TABLE_ARGS=""
for t in $TABLES; do TABLE_ARGS="$TABLE_ARGS -t $t"; done
pg_dump "$DB_URL" --data-only --no-owner --no-privileges $TABLE_ARGS | gzip > "$OUTFILE"
echo "Full backup: $OUTFILE ($(du -h "$OUTFILE" | cut -f1))"

# Per-tenant snapshots (leads + query logs only)
for ROW in $(psql "$DB_URL" -t -A -c "SELECT site_id, id FROM customers WHERE is_active = true;"); do
  SITE_ID=$(echo "$ROW" | cut -d'|' -f1)
  CUST_ID=$(echo "$ROW" | cut -d'|' -f2)
  TENANT_FILE="${BACKUP_DIR}/${SITE_ID}_${TIMESTAMP}.sql.gz"

  (
    psql "$DB_URL" -c "\COPY (SELECT * FROM user_profiles WHERE customer_id = '${CUST_ID}') TO STDOUT WITH CSV HEADER" 2>/dev/null
    echo "---"
    psql "$DB_URL" -c "\COPY (SELECT * FROM query_logs WHERE customer_id = '${CUST_ID}') TO STDOUT WITH CSV HEADER" 2>/dev/null
    echo "---"
    psql "$DB_URL" -c "\COPY (SELECT * FROM verification_sessions WHERE customer_id = '${CUST_ID}') TO STDOUT WITH CSV HEADER" 2>/dev/null
  ) | gzip > "$TENANT_FILE"
  echo "Tenant backup: $TENANT_FILE ($(du -h "$TENANT_FILE" | cut -f1))"
done

# Rotate: keep last 7 days of backups
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +7 -delete
echo "Rotation complete. Current backups:"
ls -lh "$BACKUP_DIR"/*.sql.gz 2>/dev/null
