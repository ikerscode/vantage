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

# SEC-06: never run as root — this process fetches and parses attacker-
# reachable URLs (see app/security.py's SSRF hardening), so it's exactly
# the kind of process where a bug turning into container-root would matter.
RUN groupadd --system vantage && useradd --system --gid vantage --no-create-home --shell /usr/sbin/nologin vantage

WORKDIR /app

# SEC-07: hash-pinned dependencies — see apps/api/Dockerfile's comment for
# the full rationale; same mechanism, this service's own requirements.lock.txt.
COPY services/tiler/requirements.lock.txt /tmp/requirements.lock.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock.txt

COPY services/tiler /app
RUN pip install --no-cache-dir --no-deps . && chown -R vantage:vantage /app

# SEC-06: read_only (compose) means no writable filesystem for pyc caching
# at import time — harmless either way, but this skips even trying.
ENV PYTHONDONTWRITEBYTECODE=1

USER vantage

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
