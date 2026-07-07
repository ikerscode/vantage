-- Runs once, automatically, on first container init (docker-entrypoint-initdb.d),
-- as the bootstrap superuser (POSTGRES_USER). Creates least-privilege roles so
-- the always-running api/worker/beat processes never connect as that
-- superuser — only the one-shot api-migrate service does (as vantage_migrate).
--
-- vantage_migrate: owns the app schema, runs Alembic migrations (CREATEDB is
--   not actually required for this but is harmless in a single-DB dev setup;
--   kept off here since it's unused — see note below).
-- vantage_app: DML only (SELECT/INSERT/UPDATE/DELETE) on tables vantage_migrate
--   creates, via a default-privileges rule — no DDL rights at all. Verified
--   empirically: this role can SELECT but gets "permission denied for schema
--   public" on CREATE TABLE.
--
-- Known scope boundary (documented, not silently swept under the rug):
-- pgstac-migrate still connects as the bootstrap superuser. pypgstac's own
-- migration performs role grants that fail under vantage_migrate even with
-- CREATEROLE ("permission denied to grant role pgstac_admin") — verified
-- empirically against a real Postgres instance. Chasing pypgstac's internal
-- grant graph further was out of scope for this pass; pgstac provisioning is
-- an infrequent operator-run bootstrap step, not part of the live request
-- path, so it stays on the bootstrap superuser rather than blocking on it.

CREATE ROLE vantage_migrate LOGIN PASSWORD 'changeme-migrate-dev' CREATEROLE;
CREATE ROLE vantage_app LOGIN PASSWORD 'changeme-app-dev';

GRANT CREATE, USAGE ON SCHEMA public TO vantage_migrate;
GRANT USAGE ON SCHEMA public TO vantage_app;

ALTER DEFAULT PRIVILEGES FOR ROLE vantage_migrate IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO vantage_app;
ALTER DEFAULT PRIVILEGES FOR ROLE vantage_migrate IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO vantage_app;
