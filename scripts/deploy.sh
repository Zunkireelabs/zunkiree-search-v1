#!/usr/bin/env bash
# deploy.sh — Deploy Zunkiree Search API on VPS.
# Usage: ./scripts/deploy.sh
#
# Pulls latest code, runs migrations, rebuilds Docker, restarts service.
# Run this from the project root on the VPS.

set -euo pipefail

PROJECT_DIR="/home/zunkireelabs/devprojects/zunkiree-search-v1"
SERVICE="zunkiree-search-api"

cd "$PROJECT_DIR"

echo "=== Zunkiree Deploy ==="
echo ""

# 1. Pull latest code
echo "1/4 Pulling latest code..."
git pull origin main
echo ""

# 2. Run migrations
echo "2/4 Running migrations..."
DB_URL=$(docker compose exec "$SERVICE" printenv DATABASE_URL 2>/dev/null | tr -d '\r' || true)
if [ -n "$DB_URL" ]; then
  ./scripts/migrate.sh "$DB_URL"
else
  echo "  ⚠ Could not read DATABASE_URL from container, skipping migrations"
  echo "  Run manually: ./scripts/migrate.sh \$DATABASE_URL"
fi
echo ""

# 3. Rebuild
echo "3/4 Building Docker image..."
docker compose build "$SERVICE"
echo ""

# 4. Restart
echo "4/4 Restarting service..."
docker compose up -d --force-recreate "$SERVICE"
echo ""

# 5. Verify
echo "Waiting for health check..."
sleep 3
if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
  echo "✓ Service is healthy"
else
  echo "⚠ Health check failed — check logs: docker logs $SERVICE --tail 20"
fi

echo ""
echo "=== Deploy complete ==="
