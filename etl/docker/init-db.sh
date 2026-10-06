#!/bin/sh
set -eu
secret_root="${FACTORED_PG_SECRET_ROOT:-/run/secrets}"
ETL_ROLE_PASSWORD="$(cat "$secret_root/etl_password")"
BCK_ROLE_PASSWORD="$(cat "$secret_root/backend_password")"
if [ -z "$ETL_ROLE_PASSWORD" ] || [ -z "$BCK_ROLE_PASSWORD" ]; then
    echo 'Application role passwords must be nonempty.' >&2
    exit 1
fi
export ETL_ROLE_PASSWORD BCK_ROLE_PASSWORD
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
\getenv etl_password ETL_ROLE_PASSWORD
\getenv backend_password BCK_ROLE_PASSWORD
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE ROLE etl_loader LOGIN PASSWORD :'etl_password';
CREATE ROLE backend_api LOGIN PASSWORD :'backend_password';
CREATE SCHEMA bank AUTHORIZATION etl_loader;
GRANT USAGE ON SCHEMA bank TO backend_api;
CREATE SCHEMA simulator AUTHORIZATION backend_api;
SQL
unset ETL_ROLE_PASSWORD BCK_ROLE_PASSWORD
