# Build context is the repo root (see infra/docker-compose.yml) so this can
# also COPY packages/geo, which apps/api depends on as a local path install.
FROM python:3.11-slim

WORKDIR /app

# packages/geo changes far less often than apps/api — its own layer to keep
# rebuilds of app code from re-installing it.
COPY packages/geo /packages/geo
RUN pip install --no-cache-dir /packages/geo

COPY apps/api /app
RUN pip install --no-cache-dir .

EXPOSE 8000

# Overridden per-service in infra/docker-compose.yml (worker/beat run celery
# instead); this default lets the image be run standalone as the API.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
