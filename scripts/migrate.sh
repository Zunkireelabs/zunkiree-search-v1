#!/usr/bin/env bash
# migrate.sh — Run pending SQL migrations against the database.
# Usage: ./scripts/migrate.sh [DATABASE_URL]
#
# If DATABASE_URL is not passed as argument, reads from backend/.env
# Tracks applied migrations in a _migrations table.
#
# CONTRACT: this script must exit non-zero on any failure. The caller
# (.github/workflows/deploy.yml and migrate.yml) treats a non-zero exit as
# a deploy abort. Do not swallow errors. set -euo pipefail enforces this:
# -e exit on any unhandled non-zero, -u error on unset vars, -o pipefail
# propagates pipe failures. The for-loop also explicitly `exit 1` on the
# first failed migration.

set -euo pipefail

DB_URL="${1:-}"

# If no URL passed, read from .env
if [ -z "$DB_URL" ]; then
  if [ -f backend/.env ]; then
    DB_URL=$(grep -E '^DATABASE_URL=' backend/.env | head -1 | cut -d'=' -f2-)
  fi
fi

if [ -z "$DB_URL" ]; then
  echo "ERROR: DATABASE_URL not found. Pass as argument or set in backend/.env"
  exit 1
fi

MIGRATIONS_DIR="backend/migrations"

# Ensure tracking table exists
psql "$DB_URL" -q -c "
CREATE TABLE IF NOT EXISTS _migrations (
  id SERIAL PRIMARY KEY,
  filename VARCHAR(255) UNIQUE NOT NULL,
  applied_at TIMESTAMP DEFAULT NOW()
);
" 2>/dev/null

echo "=== Zunkiree Migration Runner ==="
echo ""

APPLIED=0
SKIPPED=0

for file in $(ls "$MIGRATIONS_DIR"/*.sql 2>/dev/null | sort); do
  filename=$(basename "$file")

  # Check if already applied
  exists=$(psql "$DB_URL" -tAc "SELECT 1 FROM _migrations WHERE filename = '$filename'" 2>/dev/null)
  if [ "$exists" = "1" ]; then
    SKIPPED=$((SKIPPED + 1))
    continue
  fi

  echo "Applying: $filename"
  if psql "$DB_URL" -f "$file" -q 2>&1; then
    psql "$DB_URL" -q -c "INSERT INTO _migrations (filename) VALUES ('$filename')" 2>/dev/null
    APPLIED=$((APPLIED + 1))
    echo "  ✓ Done"
  else
    echo "  ✗ FAILED — stopping migration"
    exit 1
  fi
done

echo ""
echo "Applied: $APPLIED | Skipped (already applied): $SKIPPED"
echo "=== Migration complete ==="
