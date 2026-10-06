"""Apply the backend-owned narrow handoff grants only in a marked synthetic demo DB."""

import json
import os
import time
from pathlib import Path

import psycopg

from factored_bank.demo.fixture import DemoSource
from factored_bank.etl.common import database_kwargs


def main():
    os.umask(0o077)
    deadline = time.monotonic() + 120
    while True:
        try:
            with psycopg.connect(**database_kwargs()) as connection:
                manifests = connection.execute("SELECT manifest FROM bank.releases").fetchall()
                current = connection.execute(
                    "SELECT release_id FROM bank.current_release"
                ).fetchone()
                if not current or not manifests:
                    if time.monotonic() >= deadline:
                        raise ValueError("demo_grant_readiness_timeout")
                    time.sleep(1)
                    continue
                if any(
                    manifest[0].get("source") != DemoSource.descriptor
                    or manifest[0].get("source_kind") != "team_generated_fixture"
                    for manifest in manifests
                ):
                    raise ValueError("refuse_grants_outside_synthetic_demo")
                connection.execute(
                    "SELECT set_config('factored_bck.backend_role', 'backend_api', true)"
                )
                connection.execute(Path("/bootstrap/handoff-read-grants.sql").read_text())
            break
        except psycopg.errors.UndefinedTable:
            if time.monotonic() >= deadline:
                raise ValueError("demo_grant_readiness_timeout") from None
            time.sleep(1)
    print(json.dumps({"status": "ready", "checks": ["synthetic_only_narrow_handoff_grants"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
