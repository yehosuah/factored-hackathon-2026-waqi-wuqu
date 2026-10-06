#!/bin/sh
# Read host-private secrets as root, then let PostgreSQL drop to its own UID.
set -eu

secret_root=/run/factored-secrets
if [ "$(id -u)" != 0 ]; then
    echo 'PostgreSQL bootstrap requires its initial root entrypoint.' >&2
    exit 1
fi
mkdir -p "$secret_root"
if [ -L "$secret_root" ]; then
    echo 'Unsafe PostgreSQL runtime secret directory.' >&2
    exit 1
fi
chmod 700 "$secret_root"
for name in postgres_password etl_password backend_password; do
    source="/run/secrets/$name"
    target="$secret_root/$name"
    if [ -L "$source" ] || [ ! -f "$source" ] || [ ! -s "$source" ] || [ -L "$target" ]; then
        echo 'Missing, empty or unsafe PostgreSQL bootstrap secret.' >&2
        exit 1
    fi
    cp "$source" "$target"
    chmod 600 "$target"
    chown postgres:postgres "$target"
done
chown postgres:postgres "$secret_root"
export POSTGRES_PASSWORD_FILE="$secret_root/postgres_password"
export FACTORED_PG_SECRET_ROOT="$secret_root"
exec /usr/local/bin/docker-entrypoint.sh "$@"
