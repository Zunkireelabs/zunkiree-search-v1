FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Don't copy .env into the image
# (env vars should come from docker-compose or host)

EXPOSE 8000

# Use 2 workers for production, auto-detect concurrency.
# NOTE: DB pool sizing (app/database.py) divides a total socket budget by the
# worker count to stay under Supavisor's shared 15-connection ceiling. If you
# change --workers here, either set UVICORN_WORKERS to match (see
# docker-compose.yml environment block) or update database.py's fallback.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
