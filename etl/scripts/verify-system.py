"""Verify the running Compose API with isolated team fixtures; never print source rows/secrets."""

import json
import subprocess
import sys
from pathlib import Path


def inside():
    import secrets
    from concurrent.futures import ThreadPoolExecutor
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen
    from uuid import uuid4

    from factored_bck.security import password_hash
    from factored_bck.settings import Settings
    from factored_bck.store import Store

    db = Store(Settings())
    tag = uuid4().hex[:12]
    username, customer = "verify-" + tag, "TEAM-VERIFY-" + tag
    password = secrets.token_urlsafe(32)
    prefix = "TEAM-VERIFY-CARD-" + tag
    checks = []
    source_username = "verify-source-" + tag
    source_key = "source-dispute-" + tag
    source_customer = None

    def request(path, body=None, token=None, key=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        if key:
            headers["Idempotency-Key"] = key
        req = Request(
            "http://127.0.0.1:8000" + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,
        )
        try:
            with urlopen(req, timeout=30) as response:
                return response.status, json.load(response)
        except HTTPError as response:
            return response.code, json.load(response)

    with db.connect() as pg:
        pg.execute(
            "INSERT INTO simulator.users VALUES(%s,%s,%s,%s)",
            (username, password_hash(password), customer, "team_synthetic"),
        )
        for suffix, state, owner in [
            ("active", "ACTIVE", customer),
            ("pending", "PENDING_ACTIVATION", customer),
            ("blocked", "BLOCKED", customer),
            ("other", "ACTIVE", customer + "-other"),
        ]:
            pg.execute(
                "INSERT INTO simulator.fixture_cards VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    prefix + suffix,
                    owner,
                    "Tarjeta Crédito",
                    "TEAM-TEST-4242",
                    "USD",
                    "125.50",
                    "1000.00",
                    state,
                    "team_synthetic",
                ),
            )
            pg.execute(
                "INSERT INTO simulator.card_states(product_id,customer_id,state) VALUES(%s,%s,%s)",
                (prefix + suffix, owner, state),
            )
    try:
        assert request("/health/ready")[0] == 200
        assert request("/me/cards")[0] == 401
        assert request("/auth/login", {"username": username, "password": "wrong"})[0] == 401
        code, login = request("/auth/login", {"username": username, "password": password})
        assert code == 200
        token = login["access_token"]
        checks.append("authenticated_session")
        code, listing = request("/me/cards", token=token)
        assert code == 200 and len(listing["cards"]) == 3
        assert all(
            "product_number" not in c and c["source_kind"] == "team_synthetic"
            for c in listing["cards"]
        )
        assert request("/me/cards/" + prefix + "other", token=token)[0] == 404
        assert (
            request(
                "/me/cards/" + prefix + "other/actions", {"action": "block"}, token, "other-action"
            )[0]
            == 404
        )
        checks.extend(["customer_isolation", "number_masking", "fixture_provenance"])
        endpoint = "/me/cards/" + prefix + "active/actions"
        with ThreadPoolExecutor(max_workers=4) as pool:
            repeated = list(
                pool.map(
                    lambda _: request(endpoint, {"action": "pause"}, token, "same-action"), range(4)
                )
            )
        assert all(code == 200 for code, _ in repeated)
        assert len({result["action_id"] for _, result in repeated}) == 1
        assert all(result["simulator_state"] == "PAUSED" for _, result in repeated)
        assert request(endpoint, {"action": "block"}, token, "same-action")[0] == 409
        checks.extend(["concurrent_idempotency", "conflicting_key_rejected"])
        assert (
            request(endpoint, {"action": "reactivate"}, token, "reactivate")[1]["simulator_state"]
            == "ACTIVE"
        )
        assert (
            request(endpoint, {"action": "block"}, token, "block")[1]["simulator_state"]
            == "BLOCKED"
        )
        assert request(endpoint, {"action": "reactivate"}, token, "after-block")[0] == 409
        pending = "/me/cards/" + prefix + "pending/actions"
        assert (
            request(pending, {"action": "activate"}, token, "activate")[1]["simulator_state"]
            == "ACTIVE"
        )
        checks.extend(["pause_reactivation", "loss_theft_not_reversible", "initial_activation"])
        _, replacement = request(endpoint, {"action": "replacement"}, token, "replacement")
        assert (
            replacement["outcome"] == "replacement_request_registered"
            and replacement["simulated"] is True
        )
        assert "request_id" in replacement and "shipping" not in replacement
        checks.append("replacement_request_only")
        assert (
            request(endpoint, {"action": "pause", "customer_id": "other"}, token, "override")[0]
            == 422
        )
        assert (
            request(endpoint, {"action": "unrecognized-charge"}, token, "incomplete-dispute")[0]
            == 422
        )
        assert request(endpoint, {"action": "refund"}, token, "unsupported")[0] == 422
        checks.append("invalid_and_unsupported_actions_rejected")
        code, handoff = request("/me/handoff", token=token)
        assert code == 200 and len(handoff["verified_action_results"]) == 5
        assert all(r["result"]["status"] == "succeeded" for r in handoff["verified_action_results"])
        checks.append("audited_verified_handoff")
        assert request("/operations/etl", token=token)[1]["accepted_release"] is not None
        with db.connect() as pg:
            permission = pg.execute(
                "SELECT has_table_privilege(current_user,'bank.products','UPDATE') AS update,"
                "has_table_privilege(current_user,'bank.call_transcripts','SELECT') AS transcripts"
            ).fetchone()
            assert not permission["update"] and not permission["transcripts"]
        checks.append("database_role_restrictions")
        with db.connect() as pg:
            source = pg.execute(
                "SELECT t.customer_id,t.product_id,t.transaction_id,t.process_date "
                "FROM bank.transactions t JOIN bank.products p "
                "ON p.release_id=t.release_id AND p.product_id=t.product_id "
                "AND p.customer_id=t.customer_id WHERE t.release_id="
                "(SELECT release_id FROM bank.current_release WHERE singleton) "
                "AND p.product_type=ANY(%s) LIMIT 1",
                (["Tarjeta Crédito", "Tarjeta Débito"],),
            ).fetchone()
            assert source is not None
            source_customer = source["customer_id"]
            pg.execute(
                "INSERT INTO simulator.users VALUES(%s,%s,%s,%s)",
                (source_username, password_hash(password), source_customer, "organizer_synthetic"),
            )
        code, source_login = request(
            "/auth/login", {"username": source_username, "password": password}
        )
        assert code == 200
        source_token = source_login["access_token"]
        source_endpoint = "/me/cards/" + source["product_id"]
        code, historical = request(source_endpoint, token=source_token)
        assert code == 200 and historical["card"]["balance_semantics"] == "historical_source_value"
        assert historical["card"]["source_kind"] == "organizer_synthetic"
        code, movement = request(source_endpoint + "/movements?limit=1", token=source_token)
        assert code == 200 and len(movement["movements"]) == 1
        code, dispute = request(
            source_endpoint + "/actions",
            {
                "action": "unrecognized-charge",
                "transaction_id": source["transaction_id"],
                "process_date": source["process_date"].isoformat(),
            },
            source_token,
            source_key,
        )
        assert code == 200 and dispute["outcome"] == "request_registered_for_human_review"
        assert dispute["simulated"] and "refund" not in dispute
        checks.extend(
            [
                "accepted_organizer_consumer_read",
                "historical_movement_read",
                "unrecognized_charge_request_only",
            ]
        )
        with db.connect() as pg:
            pg.execute(
                "UPDATE simulator.sessions SET expires_at=now()-interval '1 minute' "
                "WHERE username=%s",
                (username,),
            )
        assert request("/me/cards", token=token)[0] == 401
        code, login = request("/auth/login", {"username": username, "password": password})
        assert code == 200
        token = login["access_token"]
        checks.append("expired_session_rejected")
        assert request("/auth/logout", {}, token)[0] == 200
        assert request("/me/cards", token=token)[0] == 401
        checks.append("revoked_session_rejected")
        return {
            "status": "verified",
            "data_sources": ["isolated_team_generated_fixtures", "accepted_organizer_read"],
            "checks": checks,
        }
    finally:
        with db.connect() as pg:
            pg.execute("DELETE FROM simulator.sessions WHERE username=%s", (source_username,))
            pg.execute(
                "DELETE FROM simulator.actions WHERE customer_id=%s AND idempotency_key=%s",
                (source_customer, source_key),
            )
            pg.execute("DELETE FROM simulator.users WHERE username=%s", (source_username,))
            pg.execute("DELETE FROM simulator.sessions WHERE username=%s", (username,))
            pg.execute("DELETE FROM simulator.actions WHERE customer_id=%s", (customer,))
            pg.execute(
                "DELETE FROM simulator.card_states WHERE product_id LIKE %s", (prefix + "%",)
            )
            pg.execute(
                "DELETE FROM simulator.fixture_cards WHERE product_id LIKE %s", (prefix + "%",)
            )
            pg.execute("DELETE FROM simulator.users WHERE username=%s", (username,))


def main():
    if "--inside" in sys.argv:
        try:
            print(json.dumps(inside(), sort_keys=True))
            return 0
        except Exception as exc:
            print(json.dumps({"status": "failed", "error_type": type(exc).__name__}))
            return 1
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "backend", "python", "-", "--inside"],
        input=Path(__file__).read_text(),
        text=True,
        capture_output=True,
    )
    print(result.stdout.strip())
    if result.returncode and result.stderr:
        print("Container verification failed; check service health.")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
