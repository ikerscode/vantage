# SEC-01/SEC-07: pgstac-migrate previously ran `pip install pypgstac` at
# CONTAINER STARTUP (docker-compose.yml's old `command:`), needing internet
# every time the stack came up — a real air-gap violation, and an unpinned
# one (whatever pypgstac happened to resolve to that day). Baking it into
# the image at BUILD time instead means: (a) the running container needs
# zero internet, matching every other service's air-gap posture, and (b)
# the exact version+hash is pinned via requirements.lock.txt, regenerate
# with `pip-compile --generate-hashes --allow-unsafe` if pypgstac's pin
# in this need ever changes.
FROM python:3.11-slim

RUN groupadd --system vantage && useradd --system --gid vantage --no-create-home --shell /usr/sbin/nologin vantage

COPY infra/pgstac-migrate/requirements.lock.txt /tmp/requirements.lock.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock.txt

ENV PYTHONDONTWRITEBYTECODE=1
USER vantage

# The actual migrate command (needs $POSTGRES_USER/$POSTGRES_PASSWORD/$POSTGRES_DB
# from env_file) is passed as this image's CMD override in
# docker-compose.yml/docker-compose.prod.yml — same pattern as api-migrate.
CMD ["sh", "-c", "pypgstac migrate --dsn postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@db:5432/$POSTGRES_DB"]
