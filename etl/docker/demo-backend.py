"""Provision idempotent fixture accounts inside the separate synthetic demo only."""

import json
from pathlib import Path

from factored_bck.handoff_store import HandoffStore
from factored_bck.security import password_hash, password_matches
from factored_bck.settings import Settings
from factored_bck.store import Store


def main():
    store = Store(Settings())
    with store.connect() as pg:
        manifests = pg.execute("SELECT manifest FROM bank.releases").fetchall()
        if not manifests or any(
            row["manifest"].get("source_kind") != "team_generated_fixture"
            or row["manifest"].get("source", {}).get("bucket") != "factored-local-demo"
            for row in manifests
        ):
            raise ValueError("refuse_accounts_outside_synthetic_demo")
    store.initialize()
    handoffs = HandoffStore(store)
    handoffs.check_configuration()
    password = Path("/run/secrets/other_demo_password").read_text().strip()
    with store.connect() as pg:
        existing = pg.execute(
            "SELECT * FROM simulator.users WHERE username='demo-other' FOR UPDATE"
        ).fetchone()
        if existing is None:
            pg.execute(
                "INSERT INTO simulator.users VALUES(%s,%s,%s,%s)",
                ("demo-other", password_hash(password), "DEMO-CUSTOMER-OTHER", "team_synthetic"),
            )
        elif (
            existing["customer_id"] != "DEMO-CUSTOMER-OTHER"
            or existing["source_kind"] != "team_synthetic"
            or not password_matches(password, existing["password_hash"])
        ):
            raise ValueError("demo_customer_account_conflict")
    password = Path("/run/secrets/agent_password").read_text().strip()
    with store.connect() as pg:
        existing = pg.execute(
            "SELECT * FROM simulator.agent_users WHERE username='demo-agent'"
        ).fetchone()
    if existing is None:
        handoffs.agents.provision("demo-agent", "DEMO-AGENT-001", password)
    elif existing["agent_id"] != "DEMO-AGENT-001" or not password_matches(
        password, existing["password_hash"]
    ):
        raise ValueError("demo_agent_account_conflict")
    print(
        json.dumps({"status": "ready", "checks": ["separate_fixture_customer_and_agent_accounts"]})
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
