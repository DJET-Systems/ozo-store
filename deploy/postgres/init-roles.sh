#!/usr/bin/env bash
set -euo pipefail

APP_PW="${DJET_APP_DB_PASSWORD:?DJET_APP_DB_PASSWORD is required}"
RO_PW="${DJET_RO_DB_PASSWORD:?DJET_RO_DB_PASSWORD is required}"

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  -v app_pw="$APP_PW" \
  -v ro_pw="$RO_PW" <<'EOSQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'djet_app') THEN
    CREATE ROLE djet_app LOGIN PASSWORD 'placeholder';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'djet_ro') THEN
    CREATE ROLE djet_ro LOGIN PASSWORD 'placeholder';
  END IF;
END
$$;

ALTER ROLE djet_app WITH LOGIN PASSWORD :'app_pw';
ALTER ROLE djet_ro WITH LOGIN PASSWORD :'ro_pw';

REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO djet_app;
GRANT USAGE ON SCHEMA public TO djet_ro;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO djet_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO djet_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON TABLES TO djet_ro;
EOSQL
