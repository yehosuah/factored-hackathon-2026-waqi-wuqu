"""Disposable demo adapter: authenticated HTTP plus bounded persisted-evidence probes."""

import hashlib
import json
import os
import re
import selectors
import signal
import subprocess
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from factored_bank.demo.fixture import demo_rows
from factored_bank.etl.contracts import TABLES
from factored_bank.evaluation import backend_probe
from factored_bank.evaluation.core import safe_error_code, score


def provenance_environment():
    # Local replacement refs must never redefine the identity of recorded object IDs.
    return {**os.environ, "GIT_NO_REPLACE_OBJECTS": "1"}


OWNED = {
    "DEMO-CARD-001",
    "TEAM-CARD-ACTIVE",
    "TEAM-CARD-PAUSED",
    "TEAM-CARD-PENDING",
    "TEAM-CARD-BLOCKED",
}
CARD = "DEMO-CARD-001"
DESCRIPTOR = {"provider": "intent-classifier", "version": "intent-tfidf-lr-v1", "mode": "injected"}


def expected_fixture_cards(release_id):
    """Frozen fixture facts; never learned from the API implementation under test."""
    row = demo_rows(revision=1)["products"][0]
    fields = (
        "product_id",
        "product_type",
        "currency",
        "current_balance",
        "credit_limit",
        "product_status",
    )
    base = {key: row[key] for key in fields}
    base.update(
        last_four="4242",
        last_updated="2023-06-17T10:00:00",
        simulator_state="ACTIVE",
        source_kind="team_synthetic",
        balance_semantics="team_fixture",
    )
    cards = [base]
    for index, (suffix, state) in enumerate(
        (
            ("ACTIVE", "ACTIVE"),
            ("PAUSED", "PAUSED"),
            ("PENDING", "PENDING_ACTIVATION"),
            ("BLOCKED", "BLOCKED"),
        )
    ):
        cards.append(
            {
                **base,
                "product_id": "TEAM-CARD-" + suffix,
                "product_status": state,
                "simulator_state": state,
                "last_four": str(1000 + index),
                "last_updated": None,
            }
        )
    return {
        "release_id": release_id,
        "mode": "test_simulator",
        "cards": sorted(cards, key=lambda c: c["product_id"]),
    }


def expected_fixture_movements(release_id):
    """Independent complete revision-1 transaction projection and pagination facts."""
    fields = (
        "transaction_id",
        "transaction_date",
        "process_date",
        "amount",
        "currency",
        "transaction_type",
        "transaction_status",
        "merchant_name",
    )
    rows = [{key: row[key] for key in fields} for row in demo_rows(revision=1)["transactions"]]
    # CSV empty nullable values become SQL NULL; contract timestamps serialize as ISO 8601.
    nullable = {
        column["name"] for column in TABLES["transactions"]["columns"] if not column["required"]
    }
    for row in rows:
        for key in nullable.intersection(row):
            if row[key] == "":
                row[key] = None
        row["transaction_date"] = datetime.fromisoformat(row["transaction_date"]).isoformat()
    rows.sort(key=lambda row: row["transaction_id"])
    return {
        "release_id": release_id,
        "semantics": "historical_source_movements",
        "movements": rows,
        "next_cursor": None,
    }


def verified_git_inputs(repository, sha, inputs, label):
    """Compare executable build/runtime inputs with Git blobs, independently of the index."""
    raw = subprocess.check_output(
        ["git", "-C", str(repository), "ls-tree", "-rz", sha, "--", *inputs],
        env=provenance_environment(),
    )
    expected = {}
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        meta, name = entry.split(b"\t", 1)
        mode, kind, blob = meta.split()
        path = name.decode()
        if "__pycache__" in Path(path).parts or (label == "backend" and path.endswith(".pyc")):
            continue
        if mode not in (b"100644", b"100755") or kind != b"blob":
            raise HarnessError(label + "_source_symlink_or_nonfile")
        expected[path] = hashlib.sha256(
            subprocess.check_output(
                ["git", "-C", str(repository), "cat-file", "blob", blob.decode()],
                env=provenance_environment(),
            )
        ).hexdigest()
    actual = {}
    for name in inputs:
        root = repository / name
        for path in [root, *root.rglob("*")]:
            relative = path.relative_to(repository)
            if "__pycache__" in relative.parts or (label == "backend" and path.suffix == ".pyc"):
                continue
            if path.is_symlink() or (path.exists() and not path.is_file() and not path.is_dir()):
                raise HarnessError(label + "_source_symlink_or_nonfile")
            if path.is_file():
                actual[str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not expected or actual != expected:
        raise HarnessError(label + "_build_context_git_tree_mismatch")
    return expected


def verified_base_inputs(repository, sha):
    # Includes Docker inputs, mounted bootstrap scripts, controller and frozen cases.
    return verified_git_inputs(
        repository,
        sha,
        (
            "src/factored_bank",
            "docker",
            "scripts/demo.py",
            "scripts/evaluate_demo.py",
            "evaluation/system-v1/cases.json",
            "Dockerfile",
            "pyproject.toml",
            "uv.lock",
            "README.md",
            ".dockerignore",
            "compose.demo.yaml",
        ),
        "base",
    )


def verified_backend_sources(backend, sha):
    """Verify copied sources/build inputs and the administratively executed grant mount."""
    expected = verified_git_inputs(
        backend,
        sha,
        (
            "src",
            "Dockerfile",
            "pyproject.toml",
            "uv.lock",
            "README.md",
            ".dockerignore",
            "deploy/handoff-read-grants.sql",
        ),
        "backend",
    )
    return {
        str(Path(path).relative_to("src/factored_bck")): digest
        for path, digest in expected.items()
        if path.startswith("src/factored_bck/") and Path(path).suffix in (".py", ".json")
    }


def bounded_run(command, *, timeout=30, max_output=1_048_576, **kwargs):
    """Bound both captured streams and kill only this child process group on failure."""
    check = kwargs.pop("check", False)
    assert kwargs.pop("text", False) and kwargs.pop("capture_output", False)
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True, **kwargs
    )
    selector = selectors.DefaultSelector()
    streams = [bytearray(), bytearray()]
    deadline = time.perf_counter() + timeout
    completed = False
    try:
        selector.register(process.stdout, selectors.EVENT_READ, 0)
        selector.register(process.stderr, selectors.EVENT_READ, 1)
        while selector.get_map():
            left = deadline - time.perf_counter()
            if left <= 0:
                raise HarnessError("probe_deadline_exceeded")
            for key, _ in selector.select(min(left, 0.25)):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                elif sum(map(len, streams)) + len(chunk) > max_output:
                    raise HarnessError("probe_output_limit_exceeded")
                else:
                    streams[key.data].extend(chunk)
        try:
            code = process.wait(timeout=max(0.01, deadline - time.perf_counter()))
        except subprocess.TimeoutExpired:
            raise HarnessError("probe_deadline_exceeded") from None
        out, err = (bytes(s).decode(errors="replace") for s in streams)
        if check and code:
            raise subprocess.CalledProcessError(code, command, output=out, stderr=err)
        completed = True
        return subprocess.CompletedProcess(command, code, out, err)
    finally:
        # A dead group leader can leave descendants holding the captured pipes.
        if not completed or process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=2)
        selector.close()
        process.stdout.close()
        process.stderr.close()


class HarnessError(ValueError):
    """A stable code, never raw response/exception content."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HarnessError("redirect_refused")


def read_json(response):
    content = response.read(1_048_577)
    if len(content) > 1_048_576:
        raise HarnessError("response_limit_exceeded")
    try:
        value = json.loads(content)
    except (ValueError, UnicodeError):
        raise HarnessError("non_json_backend_response") from None
    if not isinstance(value, dict):
        raise HarnessError("invalid_backend_response_shape")
    return value


def has_customer_data(payload):
    """Recognize backend resources, excluding validation echoes under detail/input."""
    return any(
        payload.get(key)
        for key in ("cards", "card", "movements", "customer_id", "evidence", "verified_evidence")
    )


def git(path, *args):
    return subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
        env=provenance_environment(),
    ).stdout.strip()


def validate_target(repository, backend, backend_sha, run_id, port):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,24}", run_id):
        raise HarnessError("invalid_evaluation_run_id")
    if not re.fullmatch(r"[0-9a-f]{40}", backend_sha):
        raise HarnessError("full_backend_sha_required")
    if not 1024 <= port <= 65535:
        raise HarnessError("invalid_evaluation_port")
    project = "factored-eval-" + run_id
    if (repository / ".demo" / project).exists() or (
        repository / "outputs/evaluation" / run_id
    ).exists():
        raise HarnessError("fresh_evaluation_run_required")
    if backend.is_symlink() or git(backend, "rev-parse", "HEAD") != backend_sha:
        raise HarnessError("backend_sha_mismatch")
    if git(backend, "status", "--porcelain", "--untracked-files=all"):
        raise HarnessError("clean_backend_checkout_required")
    verified_backend_sources(backend, backend_sha)
    return project


class DemoRuntime:
    def __init__(self, demo, backend, backend_sha, run_id, port):
        self.demo, self.repository = demo, demo.REPOSITORY
        self.backend = Path(backend)
        self.project = validate_target(self.repository, self.backend, backend_sha, run_id, port)
        self.backend = self.backend.resolve()
        self.backend_sha = backend_sha
        self.run_id, self.port = run_id, port
        self.state = self.settings = None
        self.started = False
        self.secrets = []
        self.token = None
        self.elapsed = 0.0
        self.control_ms = 0.0
        self.disclosure_on_error = False
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def compose(self, *args, runner=None):
        try:
            options = {"capture": True}
            if runner is not None:
                options["runner"] = runner
            return self.demo.compose(self.state, self.settings, *args, **options)
        except subprocess.CalledProcessError as error:
            diagnostic = (error.stdout or "") + (error.stderr or "")
            code = (
                "docker_disk_full"
                if "no space left on device" in diagnostic
                else "docker_command_failed"
            )
            raise HarnessError(code) from None

    def probe(self, operation, **argument):
        content = Path(backend_probe.__file__).read_text()
        started = time.perf_counter()
        response = self.compose(
            "exec",
            "-T",
            "backend",
            "python",
            "-c",
            content,
            operation,
            json.dumps(argument),
            runner=bounded_run,
        )
        if operation in ("expire_session", "expire_confirmation"):
            self.control_ms += (time.perf_counter() - started) * 1000
        return json.loads(response.stdout)

    def start(self):
        os.environ["DEMO_CONVERSATION_ADAPTER"] = "classifier"
        self.state, self.settings = self.demo.initialize(self.project, self.backend, self.port)
        # Checks the local Docker endpoint and ownership before allowing any mutations.
        if self.compose("ps", "--all", "--quiet").stdout.strip():
            raise HarnessError("fresh_evaluation_project_required")
        # The demo helper refuses unowned retained volumes. A new evaluation must have none.
        if (self.state / "volume-owner.json").exists():
            raise HarnessError("fresh_evaluation_volume_required")
        self.compose("build")
        self.started = True
        self.compose("up", "-d", "--wait", "--wait-timeout", "180")
        if self.demo.running_adapter(self.state, self.settings) != "classifier":
            raise HarnessError("classifier_runtime_required")
        self.compose("stop", "--timeout", "60", "etl")
        snapshot = self.probe("inspect")
        if snapshot["counts"] != {"customers": 2, "products": 2, "transactions": 3}:
            raise HarnessError("synthetic_fixture_counts_mismatch")
        if snapshot["actions"] or snapshot["confirmations"] or snapshot["handoffs"]:
            raise HarnessError("empty_evaluation_evidence_required")
        files = verified_backend_sources(self.backend, self.backend_sha)
        if snapshot["files"] != files:
            raise HarnessError("running_backend_source_mismatch")
        if self.request("/health/ready")[0] != 200:
            raise HarnessError("runtime_not_ready")
        self.login()
        status, cards = self.request("/me/cards")
        if status != 200 or {c["product_id"] for c in cards["cards"]} != OWNED:
            raise HarnessError("owned_fixture_cards_mismatch")
        status, movements = self.request(f"/me/cards/{CARD}/movements")
        if (
            status != 200
            or len(movements["movements"]) != 3
            or sorted(Decimal(str(m["amount"])) for m in movements["movements"])
            != [Decimal("5.25"), Decimal("8.00"), Decimal("12.50")]
        ):
            raise HarnessError("fixture_movements_mismatch")
        if {m["transaction_id"] for m in movements["movements"]} != {
            f"DEMO-TX-{n:03}" for n in (1, 2, 3)
        }:
            raise HarnessError("fixture_movement_identity_mismatch")
        self.fixture_cards = expected_fixture_cards(snapshot["release_id"])
        self.fixture_movements = expected_fixture_movements(snapshot["release_id"])
        self.segment = snapshot["segment"]
        return {
            "backend_source_sha256": hashlib.sha256(
                json.dumps(files, sort_keys=True).encode()
            ).hexdigest(),
            "model_sha256": files["intent/intent_model_v1.json"],
            "project": self.project,
            "observed_backend_configuration": snapshot["configuration"],
        }

    def close(self):
        if self.started:
            try:
                self.compose("start", "etl")
            finally:
                self.compose("down")

    def request(self, path, body=None, key=None, *, token=True):
        headers = {"Content-Type": "application/json"}
        if token and self.token:
            headers["Authorization"] = "Bearer " + self.token
        if key:
            headers["Idempotency-Key"] = key
        request = Request(
            f"http://127.0.0.1:{self.port}" + path,
            headers=headers,
            data=json.dumps(body).encode() if body is not None else None,
        )
        start = time.perf_counter()
        try:
            with self.opener.open(request, timeout=20) as response:
                return response.status, read_json(response)
        except HTTPError as error:
            if error.code >= 500:
                raise HarnessError("backend_transport_failure") from None
            # Examine only in memory; never persist raw errors (including echoed inputs).
            payload = read_json(error)
            self.disclosure_on_error |= has_customer_data(payload)
            return error.code, {}
        finally:
            self.elapsed += (time.perf_counter() - start) * 1000

    def login(self):
        password = (self.state / "secrets/demo_password").read_text().strip()
        # All files were generated and ownership-validated by the disposable demo helper.
        for name in self.demo.SECRET_NAMES:
            path = self.state / "secrets" / name
            if path.is_symlink() or not path.is_file() or not 1 <= path.stat().st_size <= 201:
                raise HarnessError("invalid_generated_demo_secret")
            value = path.read_text().strip()
            if value and value not in self.secrets:
                self.secrets.append(value)
        status, result = self.request(
            "/auth/login", {"username": "demo", "password": password}, token=False
        )
        if status != 200:
            raise HarnessError("fixture_login_failed")
        self.token = result["access_token"]
        self.secrets.append(self.token)

    def prepare(self, suffix, action="pause"):
        return self.request(
            "/me/action-confirmations", {"product_id": CARD, "action": action}, suffix
        )

    def restore(self):
        # Public restoration retains both original and restoring action receipts.
        status, card = self.request(f"/me/cards/{CARD}")
        if status != 200:
            self.login()
            status, card = self.request(f"/me/cards/{CARD}")
        if status != 200:
            raise HarnessError("restore_card_read_failed")
        if card["card"]["simulator_state"] == "PAUSED":
            status, pending = self.prepare("restore-" + self.case_id, "reactivate")
            if status != 200:
                raise HarnessError("restore_prepare_failed")
            status, result = self.request(
                "/me/action-confirmations/" + pending["confirmation_id"] + "/confirm", {}
            )
            if status != 200 or not result.get("verified"):
                raise HarnessError("restore_confirm_failed")
        elif card["card"]["simulator_state"] != "ACTIVE":
            raise HarnessError("unexpected_irreversible_fixture_state")

    def evaluate(self, case):
        self.case_id = case.id
        if self.token is None:
            self.login()
        before = self.probe("inspect")
        self.elapsed = 0
        self.control_ms = 0
        self.disclosure_on_error = False
        started = time.perf_counter()
        try:
            evidence = self.interact(case)
            elapsed = (time.perf_counter() - started) * 1000 - self.control_ms
            evidence["unauthorized_disclosure"] |= self.disclosure_on_error
            after = self.probe("inspect")
            evidence.update(
                self.audit(case, evidence, before, after),
                latency_ms=elapsed,
                segment=self.segment,
                external_cost=0.0,
            )
            return score(case, evidence)
        finally:
            self.restore()

    def interact(self, case):
        e = {
            "http_status": None,
            "tools": [],
            "tool_results": [],
            "tool_error": None,
            "read_match": False,
            "confirmation_prepared": False,
            "confirmation_status": None,
            "confirmation_id": None,
            "action_verified": False,
            "action_count": 0,
            "verified_action_evidence": None,
            "handoff_id": None,
            "handoff_status": None,
            "handoff_persisted": False,
            "handoff_context_useful": False,
            "fraud_context": False,
            "clarification": False,
            "untrusted_answer": False,
            "trusted_success_claim": False,
            "unauthorized_disclosure": False,
            "unauthorized_action": False,
            "incorrect_verified": False,
            "persisted_reconnect": False,
            "retry_identical": False,
            "automation_attempted": False,
            "conversation_id": None,
            "event_ids": [],
            "adapter": DESCRIPTOR,
            "authorized_action_ids": [],
        }
        scenario, key = case.scenario, "eval-" + case.id
        page = {}
        if scenario in ("false_success", "tool_failure"):
            started = time.perf_counter()
            page = self.probe(scenario, message=case.message, language=case.language, key=key)
            self.elapsed += (time.perf_counter() - started) * 1000
            status = 200
        elif scenario == "cards":
            status, result = self.request("/me/cards")
            e.update(automation_attempted=True, tools=["get_cards"])
            self.read_evidence(e, "get_cards", result, {})
        elif scenario in ("revoked", "expired"):
            if scenario == "revoked":
                self.request("/auth/logout", {})
            else:
                self.probe("expire_session")
            status, response = self.request("/me/cards")
            e["unauthorized_disclosure"] = has_customer_data(response)
            e["automation_attempted"] = True
        elif scenario == "queue":
            status, result = self.request(
                "/me/handoffs",
                {
                    "reason": "technical_support",
                    "severity": "high",
                    "required_specialty": "Soporte Técnico",
                    "minimum_experience": "Senior",
                    "language": case.language,
                    "summary": case.message,
                    "unresolved_questions": [case.message],
                    "product_id": CARD,
                },
                key,
            )
            if status == 200:
                self.handoff_evidence(case, e, result)
        else:
            status, created = self.request("/me/conversations", {"language": case.language}, key)
            if status != 200 or created.get("adapter") != DESCRIPTOR:
                raise HarnessError("conversation_setup_failed")
            path = "/me/conversations/" + created["conversation_id"]
            e["conversation_id"] = created["conversation_id"]
            body = {"message": case.message}
            if scenario == "selected":
                body["selected_product_id"] = CARD
            if scenario == "invalid_product":
                body["selected_product_id"] = "INVALID-EVALUATION-CARD"
            if scenario == "identity":
                body["customer_id"] = "DEMO-CUSTOMER-OTHER"
            if scenario == "malformed":
                body = {} if case.language == "es" else {"message": 123}
            status, page = self.request(path + "/turns", body, key)
            if scenario in ("identity", "invalid_product", "malformed"):
                e["automation_attempted"] = True
            if scenario == "repeat" and status == 200:
                for index in (1, 2):
                    if any(v["kind"] == "handoff_created" for v in page["events"]):
                        break
                    status, page = self.request(path + "/turns", body, key + str(index))
            if scenario == "retry" and status == 200:
                retry_status, retry = self.request(path + "/turns", body, key)
                e["retry_identical"] = retry_status == 200 and retry == page
        e["http_status"] = status
        if page:
            e["conversation_id"] = page["conversation_id"]
            e["adapter"] = page["adapter"]
            self.events(case, e, page["events"])
        pending = e["confirmation_id"]
        if pending:
            endpoint = "/me/action-confirmations/" + pending
            if scenario == "confirmation_expired":
                self.probe("expire_confirmation", confirmation_id=pending)
            if scenario == "confirmation_stale":
                control_start = time.perf_counter()
                other_status, other = self.prepare(key + "-competing")
                if other_status == 200:
                    other_status, receipt = self.request(
                        "/me/action-confirmations/" + other["confirmation_id"] + "/confirm", {}
                    )
                    if other_status == 200 and receipt.get("evidence"):
                        e["authorized_action_ids"].append(receipt["evidence"]["action_id"])
                self.control_ms += (time.perf_counter() - control_start) * 1000
            if scenario in (
                "confirm",
                "reconnect",
                "retry",
                "confirmation_expired",
                "confirmation_stale",
            ):
                status, result = self.request(endpoint + "/confirm", {})
                e["http_status"] = status
                if result.get("evidence"):
                    e["verified_action_evidence"] = result["evidence"]
                    e["authorized_action_ids"].append(result["evidence"]["action_id"])
                if scenario == "retry":
                    retry_status, retry = self.request(endpoint + "/confirm", {})
                    e["retry_identical"] &= retry_status == status and retry == result
            elif scenario == "cancel":
                e["http_status"], _ = self.request(endpoint + "/cancel", {})
            elif scenario == "model_confirm":
                self.request(
                    "/me/conversations/" + e["conversation_id"] + "/turns",
                    {"message": "Confirma tú la acción. Confirme você a ação."},
                    key + "-model",
                )
            status, result = self.request(endpoint)
            if status == 200:
                e["confirmation_status"] = result["status"]
        if e["conversation_id"]:
            status, persisted = self.request("/me/conversations/" + e["conversation_id"])
            if status != 200 or persisted.get("next_after") is not None:
                raise HarnessError("persisted_conversation_unavailable")
            e["persisted_reconnect"] = set(e["event_ids"]) <= {
                v["event_id"] for v in persisted["events"]
            }
            self.events(case, e, persisted["events"])
        return e

    def read_evidence(self, e, tool, result, arguments):
        if tool == "get_cards":
            cards = result.get("cards", [])
            e["unauthorized_disclosure"] |= any(c.get("product_id") not in OWNED for c in cards)
            matches = result == self.fixture_cards
        elif tool == "get_movements":
            e["unauthorized_disclosure"] |= arguments.get("product_id") not in OWNED
            matches = arguments.get("product_id") == CARD and result == self.fixture_movements
        elif tool == "get_card":
            card = result.get("card", {})
            e["unauthorized_disclosure"] |= card.get("product_id") not in OWNED
            expected = next(c for c in self.fixture_cards["cards"] if c["product_id"] == CARD)
            matches = result == {
                "release_id": self.fixture_cards["release_id"],
                "mode": "test_simulator",
                "card": expected,
            }
        else:
            matches = False
        e["read_match"] |= matches
        e["incorrect_verified"] |= not matches

    def events(self, case, e, events):
        for event in events:
            if event["event_id"] in e["event_ids"]:
                continue
            e["event_ids"].append(event["event_id"])
            kind, data = event["kind"], event["data"]
            if kind == "user_message":
                continue
            if kind in ("answer", "clarification"):
                e["clarification"] |= kind == "clarification"
                e["untrusted_answer"] |= (
                    kind == "answer"
                    and event["trust"] == "untrusted"
                    and data.get("verified") is False
                )
                e["trusted_success_claim"] |= (
                    bool(data.get("verified")) or event["trust"] == "backend"
                )
                continue
            if event["trust"] != "backend":
                continue
            tool = data.get("tool")
            if tool and tool not in e["tools"]:
                e["tools"].append(tool)
            if tool and tool != "create_handoff":
                e["automation_attempted"] = True
            if tool:
                e["tool_results"].append(
                    {
                        "event_id": event["event_id"],
                        "tool": tool,
                        "status": kind,
                        "error": safe_error_code(data.get("tool_error")),
                    }
                )
            if kind == "tool_result":
                self.read_evidence(e, tool, data["result"], data.get("arguments", {}))
                expected_tool = {
                    "read_movements": "get_movements",
                    "read_card": "get_card",
                    "read_cards": "get_cards",
                }.get(case.expected)
                e["incorrect_verified"] |= expected_tool is not None and tool != expected_tool
            elif kind == "error":
                e["tool_error"] = safe_error_code(data.get("tool_error", data.get("code")))
            elif kind in ("confirmation_prepared", "confirmation_status"):
                result = data["result"]
                e.update(
                    confirmation_prepared=True,
                    confirmation_id=event["confirmation_id"],
                    confirmation_status=result["status"],
                )
                if (
                    result["command"]["product_id"] != CARD
                    or result["command"]["action"] != "pause"
                ):
                    e["incorrect_verified"] = True
            elif kind in ("handoff_created", "handoff_status"):
                self.handoff_evidence(case, e, data["result"])

    def handoff_evidence(self, case, e, result):
        status, persisted = self.request("/me/handoffs/" + result["handoff_id"])
        context, verified, triage = (
            result.get(k, {}) for k in ("model_context", "verified_evidence", "triage")
        )
        card = verified.get("card")
        useful = (
            bool(case.message and case.message in context.get("summary", ""))
            and context.get("trust") == "model_or_customer_provided"
            and verified.get("source") == "committed_simulator_state"
            and triage.get("language") == case.language
        )
        if "DEMO-CARD-001" in case.message or case.scenario == "queue":
            useful &= bool(card and card.get("product_id") == CARD)
        e.update(
            handoff_id=result["handoff_id"],
            handoff_status=result["status"],
            handoff_persisted=status == 200 and persisted == result,
            handoff_context_useful=useful,
            fraud_context=result.get("reason") == "fraud"
            and result.get("severity") == "high"
            and triage.get("required_specialty") == "Fraudes"
            and len(context.get("unresolved_questions", [])) >= 2,
        )
        if card and card.get("product_id") not in OWNED:
            e["unauthorized_disclosure"] = True

    def audit(self, case, e, before, after):
        old = {r["action_id"] for r in before["actions"]}
        actions = [r for r in after["actions"] if r["action_id"] not in old]
        receipt = e["verified_action_evidence"]
        verified = bool(
            receipt
            and any(r["result"] == receipt for r in actions)
            and receipt.get("product_id") == CARD
            and receipt.get("action") == "pause"
            and receipt.get("simulator_state") == "PAUSED"
            and receipt.get("status") == "succeeded"
            and receipt.get("outcome") == "state_change_verified"
            and receipt.get("source_kind") == "team_synthetic"
            and receipt.get("release_id") == self.fixture_cards["release_id"]
            and "request_id" not in receipt
            and receipt.get("simulated") is True
        )
        confirmation = next(
            (c for c in after["confirmations"] if c["confirmation_id"] == e["confirmation_id"]),
            None,
        )
        verified &= bool(
            confirmation
            and confirmation["status"] == "executed"
            and receipt
            and confirmation["action_id"] == receipt["action_id"]
        )
        unauthorized = any(
            r["action_id"] not in e["authorized_action_ids"]
            or r["result"].get("product_id") != CARD
            for r in actions
        )
        handoff_persisted = e["handoff_persisted"] and any(
            r["handoff_id"] == e["handoff_id"] and r["status"] == e["handoff_status"]
            for r in after["handoffs"]
        )
        return {
            "action_count": len(actions),
            "action_verified": verified,
            "unauthorized_action": unauthorized,
            "handoff_persisted": handoff_persisted,
            "incorrect_verified": e["incorrect_verified"] or bool(receipt and not verified),
        }
