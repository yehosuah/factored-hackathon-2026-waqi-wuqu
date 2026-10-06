"""Verify actual action/audit persistence through Compose restart and an ETL repeat."""

import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

SETUP = """
import json
from uuid import uuid4
from factored_bck.settings import Settings
from factored_bck.store import Store
db=Store(Settings())
tag='TEAM-RESTART-'+uuid4().hex
with db.connect() as pg:
    pg.execute("INSERT INTO simulator.fixture_cards VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
               (tag,tag,'Tarjeta Crédito','TEAM-TEST-1111','USD','1.00',
                None,'ACTIVE','team_synthetic'))
    pg.execute("INSERT INTO simulator.card_states(product_id,customer_id,state) "
               "VALUES(%s,%s,%s)",(tag,tag,'ACTIVE'))
result=db.action({'customer_id':tag},tag,'pause',tag)
print(json.dumps({'tag':tag,'action_id':result['action_id']}))
"""
CHECK = """
import json,sys
from factored_bck.settings import Settings
from factored_bck.store import Store
db=Store(Settings()); probe=json.loads(sys.argv[1]); tag=probe['tag']
try:
    with db.connect() as pg:
        state=pg.execute("SELECT state FROM simulator.card_states WHERE product_id=%s",
                         (tag,)).fetchone()
        result=pg.execute("SELECT result FROM simulator.actions WHERE action_id=%s",
                          (probe['action_id'],)).fetchone()
        assert state['state']=='PAUSED' and result['result']['simulator_state']=='PAUSED'
        assert db.card({'customer_id':tag},tag)['card']['simulator_state']=='PAUSED'
    print(json.dumps({'status':'verified','checks':['simulator_state_persisted','verified_audit_persisted','etl_repeat_preserves_actions']}))
finally:
    with db.connect() as pg:
        pg.execute("DELETE FROM simulator.actions WHERE customer_id=%s",(tag,))
        pg.execute("DELETE FROM simulator.card_states WHERE product_id=%s",(tag,))
        pg.execute("DELETE FROM simulator.fixture_cards WHERE product_id=%s",(tag,))
"""


def main():
    current = json.loads(Path("data/processed/current.json").read_text())["release_id"]
    setup = subprocess.run(
        ["docker", "compose", "exec", "-T", "backend", "python", "-"],
        input=SETUP,
        text=True,
        capture_output=True,
        check=True,
    )
    probe = json.loads(setup.stdout)
    restart_at = datetime.now(UTC)
    subprocess.run(
        ["docker", "compose", "restart", "backend", "etl"], capture_output=True, check=True
    )
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        try:
            run = json.loads(Path("data/processed/status.json").read_text())
            if (
                datetime.fromisoformat(run["started_at"]) >= restart_at
                and run["status"] == "succeeded"
            ):
                assert run["release_id"] == current and run["result"]["reused"] is True
                break
        except (OSError, json.JSONDecodeError):
            pass
        time.sleep(1)
    else:
        raise RuntimeError("restart_repeat_not_completed")
    check = subprocess.run(
        ["docker", "compose", "exec", "-T", "backend", "python", "-", json.dumps(probe)],
        input=CHECK,
        text=True,
        capture_output=True,
    )
    print(check.stdout.strip())
    return check.returncode


if __name__ == "__main__":
    raise SystemExit(main())
