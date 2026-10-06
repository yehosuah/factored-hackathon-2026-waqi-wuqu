"""Exercise Linux UID permissions in a disposable volume with invented private files.

Uses the locally cached alpine:3.20 image, no network, source data, or credentials.
"""

import json
import os
import subprocess
import time
from pathlib import Path
from uuid import uuid4

IMAGE = "alpine:3.20"
ROOT = Path(__file__).resolve().parents[1]


def docker(*args, check=True, **kwargs):
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check, **kwargs)


def verify_private_secrets(volume, runtime_user):
    container = volume + "-pg"
    mount = f"type=volume,source={volume},target=/run/secrets,readonly"
    try:
        docker(
            "run",
            "-d",
            "--pull=never",
            "--network=none",
            "--name",
            container,
            "--mount",
            mount,
            "--mount",
            f"type=bind,source={ROOT / 'docker/init-db.sh'},"
            "target=/docker-entrypoint-initdb.d/10-roles.sh,readonly",
            "--mount",
            f"type=bind,source={ROOT / 'docker/pg-entrypoint.sh'},"
            "target=/usr/local/bin/factored-pg-entrypoint.sh,readonly",
            "--tmpfs",
            "/run/factored-secrets:mode=0700",
            "--tmpfs",
            "/var/lib/postgresql/data:mode=0700",
            "-e",
            "POSTGRES_USER=factored_admin",
            "-e",
            "POSTGRES_DB=factored",
            "-e",
            "POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password",
            "-e",
            "POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256",
            "--entrypoint",
            "/bin/sh",
            "postgres:17.11-alpine",
            "/usr/local/bin/factored-pg-entrypoint.sh",
            "postgres",
        )
        for role, name in (("etl_loader", "etl_password"), ("backend_api", "backend_password")):
            command = (
                f"PGPASSWORD=$(cat /run/secrets/{name}) "
                f"psql -h 127.0.0.1 -U {role} -d factored -Atc 'SELECT current_user'"
            )
            for _ in range(80):
                result = docker(
                    "exec", "--user", runtime_user, container, "sh", "-ec", command, check=False
                )
                if result.returncode == 0:
                    assert result.stdout.strip() == role
                    break
                time.sleep(0.25)
            else:
                raise RuntimeError("private_secret_role_authentication_failed")
        docker(
            "exec",
            "--user",
            "0:0",
            container,
            "sh",
            "-ec",
            "test $(stat -c %a /run/secrets/etl_password) = 600; "
            "test $(stat -c %u /run/secrets/etl_password) = 1000; "
            "test $(stat -c %a /run/factored-secrets/etl_password) = 600; "
            "test $(stat -c %u /run/factored-secrets/etl_password) = $(id -u postgres)",
        )
    finally:
        docker("rm", "-fv", container, check=False)


def verify():
    unset = {key: value for key, value in os.environ.items() if key not in ("ETL_UID", "ETL_GID")}
    assert docker("compose", "config", cwd=ROOT, env=unset, check=False).returncode != 0
    env = {**os.environ, "ETL_UID": "1000", "ETL_GID": "1000"}
    config = json.loads(docker("compose", "config", "--format", "json", cwd=ROOT, env=env).stdout)
    runtime_user = config["services"]["etl"]["user"]
    assert runtime_user == "1000:1000"
    assert config["services"]["backend"]["user"] == runtime_user
    assert config["services"]["postgres"]["entrypoint"] == [
        "/bin/sh",
        "/usr/local/bin/factored-pg-entrypoint.sh",
    ]
    volume = "factored-etl-permissions-" + uuid4().hex
    docker("volume", "create", volume)
    try:
        docker(
            "run",
            "--rm",
            "--pull=never",
            "--network=none",
            "--user",
            "0:0",
            "--mount",
            f"type=volume,source={volume},target=/fixture",
            IMAGE,
            "sh",
            "-ec",
            "mkdir /fixture/raw /fixture/extract /fixture/processed; "
            "printf 'invented-team-fixture\\n' > /fixture/raw/accepted.csv; "
            "chmod 700 /fixture/raw /fixture/extract /fixture/processed; "
            "for name in postgres_password etl_password backend_password; do "
            "printf 'invented-fixture-password\\n' > /fixture/$name; "
            "chmod 600 /fixture/$name; done; "
            "chmod 600 /fixture/raw/accepted.csv; chown -R 1000:1000 /fixture",
        )
        mount = f"type=volume,source={volume},target=/fixture"
        for command in ("cat /fixture/raw/accepted.csv", "touch /fixture/extract/.lock"):
            denied = docker(
                "run",
                "--rm",
                "--pull=never",
                "--network=none",
                "--user",
                "65532:65532",
                "--mount",
                mount,
                IMAGE,
                "sh",
                "-ec",
                command,
                check=False,
            )
            assert denied.returncode != 0 and "Permission denied" in denied.stderr
        docker(
            "run",
            "--rm",
            "--pull=never",
            "--network=none",
            "--user",
            runtime_user,
            "--mount",
            mount,
            IMAGE,
            "sh",
            "-ec",
            "umask 077; test -r /fixture/raw/accepted.csv; "
            "touch /fixture/extract/.lock /fixture/extract/status.json /fixture/processed/release; "
            "test $(stat -c %a /fixture/raw/accepted.csv) = 600; "
            "test $(stat -c %a /fixture/raw) = 700; "
            "test $(stat -c %a /fixture/processed/release) = 600",
        )
        verify_private_secrets(volume, runtime_user)
        return {
            "status": "verified",
            "source_kind": "team_generated_fixture",
            "checks": [
                "unset_uid_mapping_fails_fast",
                "default_uid_denied_private_read_and_write",
                "compose_owner_uid_reads_and_writes",
                "source_permissions_preserved",
                "new_output_is_private",
                "postgres_private_secret_bootstrap",
                "etl_and_backend_password_authentication",
                "host_secret_ownership_preserved",
            ],
        }
    finally:
        docker("volume", "rm", volume)


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
