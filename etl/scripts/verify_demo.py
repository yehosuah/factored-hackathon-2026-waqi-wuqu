"""Prove the disposable demo through real HTTP, roles, failures and process restarts."""

import json
import os
import subprocess
import time
from contextlib import contextmanager
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import uuid4

from demo import compose


@contextmanager
def manual_etl_window(state, settings):
    """Prevent scheduled publication from competing with destructive proof stages."""
    compose(state, settings, "stop", "--timeout", "60", "etl", capture=True)
    try:
        yield
    finally:
        compose(state, settings, "start", "etl", capture=True)


def assert_movement_turn(page, expected):
    """Prove the requested read, its owned card and the actual published payload."""
    results = [event for event in page["events"] if event["kind"] == "tool_result"]
    assert len(results) == 1
    event = results[0]
    assert event["trust"] == "backend"
    assert event["data"]["tool"] == "get_movements"
    assert event["data"]["arguments"]["product_id"] == "DEMO-CARD-001"
    assert expected["semantics"] == "historical_source_movements"
    assert len(expected["movements"]) == 3
    assert event["data"]["result"] == expected


def verify(state, settings):
    learned = os.getenv("DEMO_CONVERSATION_ADAPTER", "stub") == "classifier"

    def execute(service, script):
        if service == "etl":
            return compose(
                state,
                settings,
                "run",
                "--rm",
                "--no-deps",
                service,
                "python",
                "-c",
                script,
                capture=True,
            )
        return compose(state, settings, "exec", "-T", service, "python", "-c", script, capture=True)

    def request(path, body=None, token=None, key=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        if key:
            headers["Idempotency-Key"] = key
        req = Request(
            f"http://127.0.0.1:{settings['port']}" + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,
        )
        try:
            with urlopen(req, timeout=10) as response:
                return response.status, json.load(response)
        except HTTPError as response:
            return response.code, json.load(response)

    def ready():
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            try:
                if request("/health/ready")[0] == 200:
                    run = json.loads((state / "processed/status.json").read_text())
                    if run["status"] == "succeeded":
                        return run
            except (OSError, ValueError, URLError):
                pass
            time.sleep(1)
        raise ValueError("demo_readiness_timeout")

    def run_etl(expect_failure=False):
        try:
            result = compose(
                state,
                settings,
                "run",
                "--rm",
                "--no-deps",
                "etl",
                "factored-etl",
                "run",
                "--offline",
                "--manifest",
                "/state/extract/demo-manifest.json",
                capture=True,
            )
        except subprocess.CalledProcessError as error:
            assert expect_failure and error.returncode == 1
            run = json.loads(error.stdout)
        else:
            assert not expect_failure
            run = json.loads(result.stdout)
        return run

    def fixture(revision):
        compose(
            state,
            settings,
            "run",
            "--rm",
            "--no-deps",
            "fixture",
            "factored-demo-fixture",
            "--raw-root",
            "/state/raw",
            "--extract-root",
            "/state/extract",
            "--revision",
            str(revision),
            capture=True,
        )

    ready()
    checks = []
    role_check = execute(
        "etl",
        """
import json
import psycopg
from factored_bank.etl.common import database_kwargs
with psycopg.connect(**database_kwargs()) as pg:
    def first(query):
        return pg.execute(query).fetchone()[0]
    assert not first("SELECT has_schema_privilege(current_user,'simulator','CREATE')")
    assert first("SELECT has_table_privilege('backend_api','bank.products','SELECT')")
    assert not first("SELECT has_table_privilege('backend_api','bank.products','UPDATE')")
    assert not first("SELECT has_table_privilege('backend_api','bank.current_release','UPDATE')")
    counts={t:first('SELECT count(*) FROM bank.'+t+
                   ' WHERE release_id=(SELECT release_id FROM bank.current_release)')
            for t in ('customers','products','transactions')}
    assert counts=={'customers':2,'products':2,'transactions':3}
print(json.dumps({'status':'verified'}))
""",
    )
    assert json.loads(role_check.stdout)["status"] == "verified"
    checks.extend(("private_role_authentication_and_least_privilege", "real_etl_table_counts"))
    status, login = request(
        "/auth/login",
        {"username": "demo", "password": (state / "secrets/demo_password").read_text().strip()},
    )
    assert status == 200
    token = login["access_token"]
    assert request("/me/cards")[0] == 401
    status, cards = request("/me/cards", token=token)
    assert status == 200 and any(c["product_id"] == "DEMO-CARD-001" for c in cards["cards"])
    assert request("/me/cards/DEMO-CARD-OTHER", token=token)[0] == 404
    status, movements = request("/me/cards/DEMO-CARD-001/movements?limit=1", token=token)
    assert status == 200 and len(movements["movements"]) == 1 and movements["next_cursor"]
    cursor = movements["next_cursor"]
    status, second_page = request(
        "/me/cards/DEMO-CARD-001/movements?limit=1&cursor=" + quote(cursor), token=token
    )
    assert status == 200
    assert (
        second_page["movements"][0]["transaction_id"] != movements["movements"][0]["transaction_id"]
    )
    if learned:
        status, expected_movements = request("/me/cards/DEMO-CARD-001/movements", token=token)
        assert status == 200
    checks.extend(
        ("http_reads_real_published_card_and_movements", "authentication_and_customer_isolation")
    )
    status, agent_login = request(
        "/agent/auth/login",
        {
            "username": "demo-agent",
            "password": (state / "secrets/agent_password").read_text().strip(),
        },
    )
    assert status == 200
    agent_token = agent_login["access_token"]
    assert request("/me/cards", token=agent_token)[0] == 401
    conversations = []
    for language in ("es", "pt"):
        status, conversation = request(
            "/me/conversations", {"language": language}, token, "create-" + uuid4().hex
        )
        assert status == 200
        if learned:
            assert conversation["adapter"] == {
                "provider": "intent-classifier",
                "version": "intent-tfidf-lr-v1",
                "mode": "injected",
            }
            message = {
                "es": "Quiero consultar los movimientos de mi tarjeta DEMO-CARD-001",
                "pt": "Quero consultar as movimentações do meu cartão DEMO-CARD-001",
            }[language]
        else:
            assert conversation["adapter"]["mode"] == "stub"
            message = "/cards"
        path = "/me/conversations/" + conversation["conversation_id"]
        status, page = request(path + "/turns", {"message": message}, token, "turn-" + uuid4().hex)
        assert status == 200 and any(event["kind"] == "tool_result" for event in page["events"])
        if learned:
            assert_movement_turn(page, expected_movements)
        conversations.append((path, page["last_sequence"]))
        status, handoff = request(
            "/me/handoffs",
            {
                "reason": "card_support",
                "severity": "low",
                "required_specialty": None,
                "minimum_experience": "Junior",
                "language": language,
                "summary": "Explicit synthetic support test.",
                "product_id": "DEMO-CARD-001",
            },
            token,
            "handoff-" + uuid4().hex,
        )
        assert status == 200 and handoff["assigned_agent_id"] == "DEMO-AGENT-001"
        handoff_path = "/agent/handoffs/" + handoff["handoff_id"]
        assert request(handoff_path + "/accept", {}, agent_token)[1]["status"] == "accepted"
        assert request(handoff_path + "/resolve", {}, agent_token)[1]["status"] == "resolved"
    checks.extend(
        (
            "es_pt_handoff_uses_published_eligible_agent",
            "learned_classifier_reads_published_movements"
            if learned
            else "explicit_stub_reads_published_cards",
        )
    )
    status, own_card = request("/me/cards/DEMO-CARD-001", token=token)
    assert status == 200
    original_state = own_card["card"]["simulator_state"]
    assert original_state in ("ACTIVE", "PAUSED")
    action = "pause" if original_state == "ACTIVE" else "reactivate"
    expected_state = "PAUSED" if action == "pause" else "ACTIVE"
    key = "demo-proof-" + uuid4().hex
    status, confirmation = request(
        "/me/action-confirmations", {"product_id": "DEMO-CARD-001", "action": action}, token, key
    )
    assert status == 200 and confirmation["confirmation_required"]
    confirmation_path = "/me/action-confirmations/" + confirmation["confirmation_id"]
    status, executed = request(confirmation_path + "/confirm", {}, token)
    assert status == 200 and executed["verified"] and executed["simulated"]
    first_release = cards["release_id"]
    tamper = """
import json
from pathlib import Path
manifest=json.loads(Path('/state/extract/demo-manifest.json').read_text())
path=Path('/state/raw')/manifest['objects'][0]['local_path']
backup=Path('/state/extract/probe-backup.bin')
assert not backup.exists()
backup.write_bytes(path.read_bytes())
path.write_bytes(path.read_bytes()+b'corrupt-fixture')
"""
    restore = """
import json
from pathlib import Path
manifest=json.loads(Path('/state/extract/demo-manifest.json').read_text())
path=Path('/state/raw')/manifest['objects'][0]['local_path']
backup=Path('/state/extract/probe-backup.bin')
path.write_bytes(backup.read_bytes())
backup.unlink()
"""
    with manual_etl_window(state, settings):
        execute("etl", tamper)
        try:
            failed = run_etl(expect_failure=True)
            assert failed["status"] == "failed" and failed["error_code"] == "raw_content_mismatch"
            assert request("/health/ready")[0] == 200
            assert request("/me/cards", token=token)[1]["release_id"] == first_release
        finally:
            execute("etl", restore)
        recovered = run_etl()
        assert recovered["status"] == "succeeded" and recovered["release_id"] == first_release
        assert recovered["result"]["reused"]
        checks.extend(("failed_candidate_preserves_backend_release", "recovery_and_repeat_reuse"))
        fixture(2)
        try:
            corrected = run_etl()
            assert corrected["status"] == "succeeded" and corrected["release_id"] != first_release
            status, card = request("/me/cards/DEMO-CARD-001", token=token)
            assert status == 200 and card["card"]["current_balance"] == "126.50"
            assert card["card"]["simulator_state"] == expected_state
            assert (
                request("/me/cards/DEMO-CARD-001/movements?cursor=" + quote(cursor), token=token)[0]
                == 409
            )
            checks.append("corrected_publication_reaches_backend_and_preserves_simulator")
        finally:
            fixture(1)
            run_etl()
    compose(state, settings, "restart", "postgres", "etl", "backend", capture=True)
    ready()
    status, card = request("/me/cards/DEMO-CARD-001", token=token)
    assert status == 200 and card["card"]["simulator_state"] == expected_state
    status, persisted = request(confirmation_path, token=token)
    assert status == 200 and persisted["verified"]
    assert persisted["evidence"]["action_id"] == executed["evidence"]["action_id"]
    for path, sequence in conversations:
        status, page = request(path, token=token)
        assert status == 200 and page["last_sequence"] == sequence
    checks.append("conversation_events_persist_after_postgres_and_backend_restart")
    status, restore_command = request(
        "/me/action-confirmations",
        {"product_id": "DEMO-CARD-001", "action": "reactivate" if action == "pause" else "pause"},
        token,
        "restore-" + uuid4().hex,
    )
    assert status == 200
    restore_path = "/me/action-confirmations/" + restore_command["confirmation_id"] + "/confirm"
    assert request(restore_path, {}, token)[1]["verified"]
    assert (
        request("/me/cards/DEMO-CARD-001", token=token)[1]["card"]["simulator_state"]
        == original_state
    )
    checks.extend(
        (
            "postgres_etl_backend_restart_persists_release_and_session",
            "simulator_action_and_audit_persist",
        )
    )
    compose(state, settings, "down", capture=True)
    compose(
        state, settings, "up", "--no-build", "-d", "--wait", "--wait-timeout", "180", capture=True
    )
    ready()
    status, cold_card = request("/me/cards/DEMO-CARD-001", token=token)
    assert status == 200 and cold_card["card"]["simulator_state"] == original_state
    assert request(confirmation_path, token=token)[1]["verified"]
    for path, sequence in conversations:
        assert request(path, token=token)[1]["last_sequence"] == sequence
    checks.append("cold_recreation_reuses_private_secrets_grants_accounts_and_volume")
    return {"status": "verified", "data_source": "team_generated_fixture", "checks": checks}
