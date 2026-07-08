# Build context is the repo root (see infra/docker-compose.yml) so this can
# also COPY packages/geo, which apps/api depends on as a local path install.
FROM python:3.11-slim

# rasterio's manylinux wheel bundles GDAL/PROJ/GEOS/SQLite itself, but still
# dynamically links a couple of small system libraries at runtime that
# python:3.11-slim's minimal Debian base doesn't include. Found for real by
# BRIEF v1.5's CI (this Dockerfile had never been built by an actual
# container runtime before that — see CI_REPORT.md):
#   ImportError: libexpat.so.1: cannot open shared object file
RUN apt-get update \
    && apt-get install -y --no-install-recommends libexpat1 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# SEC-06: never run the request-handling process as root. --no-create-home
# since nothing here needs a home dir; --system for a UID with no login
# shell/password. Created before COPY so ownership can be set in one layer.
RUN groupadd --system vantage && useradd --system --gid vantage --no-create-home --shell /usr/sbin/nologin vantage

WORKDIR /app

# SEC-07: every third-party dependency (including packages/geo's own
# numpy/rasterio, already covered here) is pinned to an exact version AND
# hash — generated via `pip-compile --generate-hashes --allow-unsafe` (see
# requirements.lock.txt; regenerate with
# `pip-compile --generate-hashes --allow-unsafe -o requirements.lock.txt pyproject.toml`
# whenever pyproject.toml's dependencies change). --require-hashes makes pip
# refuse to install anything that isn't in this file with a matching hash —
# a compromised/typosquatted transitive dependency can't sneak in silently.
COPY apps/api/requirements.lock.txt /tmp/requirements.lock.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock.txt

# packages/geo changes far less often than apps/api — its own layer to keep
# rebuilds of app code from re-installing it. --no-deps: its dependencies
# are already satisfied (and hash-verified) above.
COPY packages/geo /packages/geo
RUN pip install --no-cache-dir --no-deps /packages/geo

COPY apps/api /app
RUN pip install --no-cache-dir --no-deps . && chown -R vantage:vantage /app

# SEC-06: read_only (compose) means no writable filesystem for pyc caching
# at import time — harmless either way, but this skips even trying.
ENV PYTHONDONTWRITEBYTECODE=1

USER vantage

EXPOSE 8000

# Overridden per-service in infra/docker-compose.yml (worker/beat run celery
# instead); this default lets the image be run standalone as the API.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
