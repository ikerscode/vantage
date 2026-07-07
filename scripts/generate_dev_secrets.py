#!/usr/bin/env python3
"""Generates infra/.env + infra/db-init/01-roles.sql for local dev (SEC-02,
SEC-04): every changeme-* placeholder in infra/.env.example is replaced with
a fresh, random per-checkout secret. Run this once before `docker compose up`
or before starting the native dev stack — it's the new first step, replacing
the old `cp infra/.env.example infra/.env`.

Idempotent: does nothing if infra/.env already exists. Regenerating on top
of an already-initialized Postgres data directory would desync the
generated role passwords from what's actually stored in that database —
delete infra/.env AND wipe/reinit the Postgres data volume together if you
need to force fresh secrets.
"""

import secrets
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_EXAMPLE = REPO_ROOT / "infra" / ".env.example"
ENV_OUT = REPO_ROOT / "infra" / ".env"
SQL_TEMPLATE = REPO_ROOT / "infra" / "db-init" / "01-roles.sql.template"
SQL_OUT = REPO_ROOT / "infra" / "db-init" / "01-roles.sql"

# Keys in .env.example whose value is replaced outright with a fresh token.
SECRET_KEYS = {
    "POSTGRES_PASSWORD": 32,
    "VANTAGE_MIGRATE_PASSWORD": 32,
    "MINIO_ROOT_PASSWORD": 32,
    "JWT_SECRET": 48,
    "TILER_TOKEN": 48,
    "INFERENCE_TOKEN": 48,
    "REDIS_PASSWORD": 32,
}


def render_env(secrets_map: dict[str, str], vantage_app_password: str) -> str:
    out_lines = []
    for line in ENV_EXAMPLE.read_text().splitlines():
        if "=" not in line or line.strip().startswith("#"):
            out_lines.append(line)
            continue
        key, _, _value = line.partition("=")
        if key in secrets_map:
            out_lines.append(f"{key}={secrets_map[key]}")
        elif key == "DATABASE_URL":
            out_lines.append(f"DATABASE_URL=postgresql+psycopg://vantage_app:{vantage_app_password}@db:5432/vantage")
        elif key in ("S3_SECRET_ACCESS_KEY", "AWS_SECRET_ACCESS_KEY"):
            out_lines.append(f"{key}={secrets_map['MINIO_ROOT_PASSWORD']}")
        elif key == "REDIS_URL":
            out_lines.append(f"REDIS_URL=redis://:{secrets_map['REDIS_PASSWORD']}@redis:6379/0")
        elif key == "CELERY_BROKER_URL":
            out_lines.append(f"CELERY_BROKER_URL=redis://:{secrets_map['REDIS_PASSWORD']}@redis:6379/0")
        elif key == "CELERY_RESULT_BACKEND":
            out_lines.append(f"CELERY_RESULT_BACKEND=redis://:{secrets_map['REDIS_PASSWORD']}@redis:6379/1")
        else:
            out_lines.append(line)
    return "\n".join(out_lines) + "\n"


def main() -> int:
    if ENV_OUT.exists():
        print(f"{ENV_OUT} already exists — not regenerating.")
        print("(delete it, and reinit the Postgres/MinIO data dirs, to force fresh secrets.)")
        return 0

    secrets_map = {key: secrets.token_urlsafe(length) for key, length in SECRET_KEYS.items()}
    vantage_app_password = secrets.token_urlsafe(32)

    ENV_OUT.write_text(render_env(secrets_map, vantage_app_password))
    print(f"wrote {ENV_OUT}")

    sql = SQL_TEMPLATE.read_text()
    sql = sql.replace("{{VANTAGE_MIGRATE_PASSWORD}}", secrets_map["VANTAGE_MIGRATE_PASSWORD"])
    sql = sql.replace("{{VANTAGE_APP_PASSWORD}}", vantage_app_password)
    if "{{" in sql:
        print(f"ERROR: {SQL_OUT} still has an unrendered placeholder — aborting.", file=sys.stderr)
        return 1
    SQL_OUT.write_text(sql)
    print(f"wrote {SQL_OUT}")

    print("done — every changeme-* value in infra/.env.example was replaced with a real secret.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
