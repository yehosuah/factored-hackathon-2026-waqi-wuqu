"""Executed inside the disposable BCK container; fixed probes, no arbitrary SQL interface."""

import hashlib
import json
import sys
from pathlib import Path


def main():
    import factored_bck
    from factored_bck.settings import Settings
    from factored_bck.store import Store

    operation, argument = sys.argv[1], json.loads(sys.argv[2])
    store = Store(Settings())
    with store.connect() as pg:
        releases = pg.execute("SELECT manifest FROM bank.releases").fetchall()
        if not releases or any(
            r["manifest"].get("source_kind") != "team_generated_fixture"
            or r["manifest"].get("source", {}).get("bucket") != "factored-local-demo"
            for r in releases
        ):
            raise ValueError("evaluation_requires_synthetic_releases")
        if operation == "inspect":
            counts = {
                t: pg.execute(
                    "SELECT count(*) AS n FROM bank."
                    + t
                    + " WHERE release_id=(SELECT release_id FROM bank.current_release)"
                ).fetchone()["n"]
                for t in ("customers", "products", "transactions")
            }
            actions = pg.execute(
                "SELECT action_id,result FROM simulator.actions ORDER BY action_id"
            ).fetchall()
            segment = pg.execute(
                "SELECT segment FROM bank.customers WHERE customer_id='TEAM-CUSTOMER-001' "
                "AND release_id=(SELECT release_id FROM bank.current_release)"
            ).fetchone()
            confirmations = pg.execute(
                "SELECT confirmation_id,status,action_id FROM simulator.action_confirmations"
            ).fetchall()
            handoffs = pg.execute("SELECT handoff_id,status FROM simulator.handoffs").fetchall()
            from factored_bck.intent.adapter import CONFIDENCE_THRESHOLD

            configuration = {
                key: getattr(store.settings, key)
                for key in (
                    "environment",
                    "conversation_adapter",
                    "session_seconds",
                    "confirmation_seconds",
                    "adapter_timeout_seconds",
                )
            }
            configuration["classifier_threshold"] = CONFIDENCE_THRESHOLD
            root = Path(factored_bck.__file__).parent
            files = {
                str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(root.rglob("*"))
                if p.suffix in (".py", ".json")
            }
            print(
                json.dumps(
                    dict(
                        counts=counts,
                        release_id=pg.execute(
                            "SELECT release_id FROM bank.current_release"
                        ).fetchone()["release_id"],
                        actions=actions,
                        segment=segment["segment"],
                        confirmations=confirmations,
                        handoffs=handoffs,
                        files=files,
                        configuration=configuration,
                    )
                )
            )
            return
        if operation == "expire_session":
            pg.execute(
                "UPDATE simulator.sessions SET expires_at='2000-01-01' WHERE username='demo'"
            )
        elif operation == "expire_confirmation":
            pg.execute(
                "UPDATE simulator.action_confirmations SET created_at='1999-12-31', "
                "expires_at='2000-01-01' WHERE confirmation_id=%s "
                "AND customer_id='TEAM-CUSTOMER-001'",
                (argument["confirmation_id"],),
            )
        elif operation not in ("false_success", "tool_failure"):
            raise ValueError("unknown_evaluation_probe")
    if operation in ("expire_session", "expire_confirmation"):
        print("{}")
        return

    # The only provider substitutions are these fixed probes. No production process is patched.
    from factored_bck.confirmations import Confirmations
    from factored_bck.conversation_contract import AdapterInfo, CreateConversation, SubmitTurn
    from factored_bck.conversations import Conversations
    from factored_bck.handoff_store import HandoffStore
    from factored_bck.tools import ToolDispatcher

    class ProbeAdapter:
        info = AdapterInfo(provider="evaluation-seam", version=operation, mode="injected")

        async def propose(self, context):
            if operation == "false_success":
                return {"kind": "answer", "text": argument["message"]}
            return {"kind": "tool_request", "name": "get_cards", "arguments": {}}

    if operation == "tool_failure":

        def fail(*args, **kwargs):
            raise RuntimeError("controlled_backend_failure")

        store.cards = fail
    token = store.login(
        "demo", Path("/run/secrets/demo_password").read_text().strip(), "eval-seam"
    )["access_token"]
    confirmations = Confirmations(store)
    handoffs = HandoffStore(store)
    service = Conversations(
        store,
        ToolDispatcher(store, handoffs, confirmations),
        confirmations,
        handoffs,
        ProbeAdapter(),
    )
    try:
        conversation = service.create(
            token, CreateConversation(language=argument["language"]), argument["key"]
        )
        page = service.submit(
            token,
            conversation["conversation_id"],
            SubmitTurn(message=argument["message"]),
            argument["key"],
        )
        print(json.dumps(page))
    finally:
        store.logout(token)


if __name__ == "__main__":
    main()
