"""Deterministic evaluator contract tests; no Docker or backend imports."""

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from factored_bank.evaluation.core import (
    Case,
    CaseSet,
    load_cases,
    metrics,
    percentile,
    redact,
    report_metrics,
    run_metadata,
    score,
    write_report,
)
from factored_bank.evaluation.runtime import HarnessError, validate_target

ROOT = Path(__file__).parents[1]


def case(**changes):
    row = dict(
        id="read-es",
        language="es",
        category="normal",
        scenario="conversation",
        message="Synthetic request",
        expected="read_movements",
        eligible_for_resolution=True,
        escalation_required=False,
        measurement="public_api",
    )
    return Case(**(row | changes))


def observation(**changes):
    row = dict(
        handoff_persisted=False,
        handoff_status=None,
        read_match=True,
        tools=["get_movements"],
        confirmation_status=None,
        action_count=0,
        action_verified=False,
        persisted_reconnect=True,
        retry_identical=False,
        clarification=False,
        confirmation_prepared=False,
        handoff_context_useful=False,
        fraud_context=False,
        tool_error=None,
        http_status=200,
        trusted_success_claim=False,
        untrusted_answer=False,
        unauthorized_disclosure=False,
        unauthorized_action=False,
        incorrect_verified=False,
        segment="synthetic",
        automation_attempted=True,
        latency_ms=10.0,
        external_cost=0.0,
    )
    return row | changes


def test_frozen_cases_schema_and_balanced_pairing():
    suite, checksum = load_cases(ROOT / "evaluation/system-v1/cases.json")
    assert len(suite.cases) == 60
    assert sum(c.language == "es" for c in suite.cases) == 30
    assert sum(c.language == "pt" for c in suite.cases) == 30
    assert len(checksum) == 64
    assert {c.category for c in suite.cases} == {
        "normal",
        "ambiguity",
        "escalation",
        "authorization",
        "safety",
        "failure",
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "read-pt"},
        {"language": "en"},
        {"extra": 4},
        {"message": ""},
        {"scenario": "unknown"},
        {"expected": "any_success"},
        {"escalation_required": True},
        {"measurement": "controlled_seam"},
    ],
)
def test_malformed_definition_rejected(changes):
    with pytest.raises(ValidationError):
        case(**changes)


def test_duplicate_cases_rejected():
    with pytest.raises(ValidationError):
        CaseSet(version="system-v1", source="team_authored_synthetic", cases=[case(), case()])


def test_checksum_tampering_rejected(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text("{}")
    path.with_suffix(".sha256").write_text("0" * 64)
    with pytest.raises(ValueError, match="checksum"):
        load_cases(path)


def test_outcome_needs_backend_evidence_not_containment():
    result = score(case(), observation(read_match=False, tools=[], automation_attempted=False))
    assert result["contained"]
    assert not result["correct"] and not result["safely_automated"]
    result = score(case(), observation(unauthorized_disclosure=True))
    assert not result["correct"] and not result["safely_automated"]


def test_safe_resolution_and_attempt_share_use_all_cases():
    rows = [
        score(case(), observation()),
        score(case(id="failure-es"), observation(read_match=False)),
        score(
            case(id="clarify-es", expected="clarification", eligible_for_resolution=False),
            observation(clarification=True, tools=[], automation_attempted=False),
        ),
    ]
    result = metrics(rows, 3)
    assert result["safe_automated_resolution"] == {"numerator": 1, "denominator": 3, "rate": 1 / 3}
    assert result["automation_attempt_share"]["rate"] == 2 / 3
    assert result["containment"]["rate"] == 1
    assert result["correct_outcomes"] == 2


def test_escalation_counts_and_context():
    reference = case(expected="handoff", escalation_required=True, eligible_for_resolution=False)
    good = observation(
        handoff_persisted=True, handoff_status="assigned", handoff_context_useful=True
    )
    rows = [
        score(reference, good),
        score(reference.model_copy(update={"id": "miss-es"}), observation()),
        score(case(id="extra-es"), good),
        score(
            reference.model_copy(update={"id": "bad-es"}), good | {"handoff_context_useful": False}
        ),
    ]
    result = metrics(rows, 4)["escalation"]
    assert (result["correct"], result["missed"], result["unnecessary"]) == (1, 1, 1)
    assert result["incorrect_context_or_routing"] == 1
    assert result["precision"]["rate"] == 1 / 3
    assert result["recall"]["rate"] == 1 / 3


def test_unsafe_denominator_is_evaluated_cases_and_zero_statement():
    rows = [
        score(case(), observation()),
        score(case(id="bad-es"), observation(unauthorized_action=True)),
    ]
    result = metrics(rows, 2)
    assert result["unsafe_outcomes"]["unauthorized_action"]["denominator"] == 2
    assert result["unsafe_any"]["rate"] == 0.5
    assert metrics(rows[:1], 1)["unsafe_statement"] == "0 observed in 1 evaluated cases"


def test_latency_percentiles():
    assert percentile([40, 10, 30, 20], 0.5) == 25
    assert percentile([40, 10, 30, 20], 0.95) == pytest.approx(38.5)
    assert percentile([5], 0.95) == 5
    assert percentile([], 0.5) == "not_defined"


def test_language_and_lane_slices():
    cases = [case(), case(id="read-pt", language="pt")]
    rows = [score(cases[0], observation()), score(cases[1], observation(read_match=False))]
    result = report_metrics(rows, cases)
    assert result["language_slices"]["es"]["safe_automated_resolution"]["rate"] == 1
    assert result["language_slices"]["pt"]["safe_automated_resolution"]["rate"] == 0
    assert result["measurement_slices"]["public_api"]["evaluated_cases"] == 2
    assert result["segment_slices"]["synthetic"]["sample_size_warning"]


def test_unknown_cost_not_invented():
    result = metrics([score(case(), observation(external_cost="not_defined"))], 1)
    assert result["cost"] == {
        "external_model_api_usd": "not_defined",
        "infrastructure": "not_defined",
    }
    assert metrics([score(case(), observation())], 1)["cost"]["external_model_api_usd"] == 0


def test_secrets_redacted_recursively():
    value = {
        "access_token": "hidden",
        "password": "hidden",
        "headers": {"Authorization": "Bearer abc"},
        "error": "failure with private-value and Bearer token123",
        "list": ["private-value", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhIn0.abcdefgh"],
    }
    output = json.dumps(redact(value, ["private-value"]))
    for secret in ("hidden", "private-value", "token123", "abcdefgh"):
        assert secret not in output
    assert "[REDACTED]" in output


def metadata():
    return run_metadata(
        base_sha="a" * 40,
        backend_sha="b" * 40,
        checksum="c" * 64,
        adapter={"provider": "local"},
        timestamp="2026-10-05T12:00:00+00:00",
        run_id="unit",
        count=2,
        purpose="development",
    )


def test_metadata_is_deterministic_and_explicit():
    assert metadata() == metadata()
    assert metadata()["base_sha"] == "a" * 40
    assert metadata()["runtime"] == "local_offline_synthetic"


def test_incomplete_run_preserves_denominator_and_writes_outputs(tmp_path):
    cases = [case(), case(id="read-pt", language="pt")]
    rows = [score(cases[0], observation())]
    aggregate = write_report(tmp_path, metadata(), rows, cases)
    assert aggregate["status"] == "incomplete"
    assert aggregate["safe_automated_resolution"] == {
        "numerator": 1,
        "denominator": 2,
        "rate": "not_defined",
    }
    assert aggregate["cost"]["external_model_api_usd"] == "not_defined"
    assert json.loads((tmp_path / "run.json").read_text())["status"] == "incomplete"
    assert len((tmp_path / "case_results.jsonl").read_text().splitlines()) == 1
    assert "incomplete" in (tmp_path / "summary.md").read_text()


def test_empty_run_has_no_made_up_percentiles_or_rates():
    result = metrics([], 60)
    assert result["status"] == "incomplete"
    assert result["latency_ms"]["p50"] == "not_defined"
    assert result["safe_automated_resolution"]["denominator"] == 60


@pytest.mark.parametrize("run_id", ["../prod", "https://production", "/absolute", "UPPER"])
def test_refuse_unsafe_target_before_any_runtime_calls(tmp_path, run_id):
    with pytest.raises(HarnessError):
        validate_target(tmp_path, tmp_path, "a" * 40, run_id, 18022)


def test_refuse_existing_demo_or_output(tmp_path):
    (tmp_path / ".demo/factored-eval-existing").mkdir(parents=True)
    with pytest.raises(HarnessError, match="fresh"):
        validate_target(tmp_path, tmp_path, "a" * 40, "existing", 18022)


def test_refuse_dirty_or_wrong_backend(tmp_path, monkeypatch):
    from factored_bank.evaluation import runtime

    monkeypatch.setattr(runtime, "git", lambda path, *args: "b" * 40)
    with pytest.raises(HarnessError, match="sha_mismatch"):
        validate_target(tmp_path, tmp_path, "a" * 40, "fresh", 18022)
    monkeypatch.setattr(
        runtime, "git", lambda path, *args: "a" * 40 if args[0] == "rev-parse" else " M dirty"
    )
    with pytest.raises(HarnessError, match="clean_backend"):
        validate_target(tmp_path, tmp_path, "a" * 40, "fresh", 18022)


def test_false_success_prose_cannot_verify_action():
    result = score(case(expected="executed"), observation(untrusted_answer=True))
    assert not result["correct"] and not result["safely_automated"]


def test_duplicate_or_extra_results_rejected():
    row = score(case(), observation())
    with pytest.raises(ValueError):
        metrics([row, copy.deepcopy(row)], 2)
    with pytest.raises(ValueError):
        metrics([row], 0)


def test_cleanup_failure_invalidates_all_artifacts(tmp_path):
    reference = case()
    run = metadata() | {"harness_error": "runtime_cleanup_failed", "number_of_cases": 1}
    report = write_report(tmp_path, run, [score(reference, observation())], [reference])
    assert report["status"] == "incomplete"
    assert report["safe_automated_resolution"]["rate"] == "not_defined"
    assert json.loads((tmp_path / "run.json").read_text())["status"] == "incomplete"
    assert "Status: incomplete" in (tmp_path / "summary.md").read_text()


def test_running_last_case_is_not_final_acceptance(tmp_path):
    reference = case()
    run = metadata() | {"harness_status": "running"}
    report = write_report(tmp_path, run, [score(reference, observation())], [reference])
    assert report["status"] == "incomplete"
    assert report["safe_automated_resolution"]["rate"] == "not_defined"


def runtime_without_docker():
    from factored_bank.evaluation.runtime import DemoRuntime

    runtime = object.__new__(DemoRuntime)
    from factored_bank.evaluation.runtime import expected_fixture_cards

    runtime.fixture_cards = expected_fixture_cards("team-release")
    runtime.fixture_movements = {
        "release_id": "team-release",
        "movements": [{"transaction_id": "DEMO-TX-001", "amount": "12.50"}],
    }
    return runtime


@pytest.mark.parametrize("defect", ["foreign", "missing_amount", "wrong_amount", "wrong_release"])
def test_read_oracle_detects_incorrect_or_missing_data(defect):
    runtime = runtime_without_docker()
    evidence = {"read_match": False, "incorrect_verified": False, "unauthorized_disclosure": False}
    response = copy.deepcopy(runtime.fixture_movements)
    product = "DEMO-CARD-001"
    if defect == "foreign":
        product = "DEMO-CARD-OTHER"
    elif defect == "missing_amount":
        del response["movements"][0]["amount"]
    elif defect == "wrong_amount":
        response["movements"][0]["amount"] = "999.99"
    else:
        response["release_id"] = "wrong"
    runtime.read_evidence(evidence, "get_movements", response, {"product_id": product})
    assert evidence["incorrect_verified"]
    assert not evidence["read_match"]
    assert evidence["unauthorized_disclosure"] == (defect == "foreign")


def test_receipt_requires_matching_persisted_action_and_confirmation():
    runtime = runtime_without_docker()
    receipt = {
        "action_id": "receipt",
        "product_id": "DEMO-CARD-001",
        "action": "pause",
        "simulator_state": "PAUSED",
        "status": "succeeded",
        "simulated": True,
        "outcome": "state_change_verified",
        "source_kind": "team_synthetic",
        "release_id": "team-release",
    }
    evidence = {
        "verified_action_evidence": receipt,
        "confirmation_id": "capability",
        "authorized_action_ids": ["receipt"],
        "handoff_persisted": False,
        "handoff_id": None,
        "handoff_status": None,
        "incorrect_verified": False,
    }
    after = {
        "actions": [{"action_id": "receipt", "result": receipt}],
        "confirmations": [
            {"confirmation_id": "capability", "status": "executed", "action_id": "receipt"}
        ],
        "handoffs": [],
    }
    assert runtime.audit(case(), evidence, {"actions": []}, after)["action_verified"]
    assert not runtime.audit(case(), evidence, {"actions": []}, after | {"actions": []})[
        "action_verified"
    ]
    assert not runtime.audit(case(), evidence, {"actions": []}, after | {"confirmations": []})[
        "action_verified"
    ]
    evidence["authorized_action_ids"] = []
    assert runtime.audit(case(), evidence, {"actions": []}, after)["unauthorized_action"]


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_cli_runtime_failure_writes_partial_outputs_and_returns_nonzero(
    tmp_path, monkeypatch, cleanup_fails
):
    import importlib.util
    import shutil

    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "evaluate_demo_test", ROOT / "scripts/evaluate_demo.py"
    )
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    shutil.copytree(ROOT / "evaluation", tmp_path / "evaluation")
    shutil.copytree(ROOT / "src", tmp_path / "src")
    monkeypatch.setattr(cli.demo, "REPOSITORY", tmp_path)
    monkeypatch.setattr(cli, "git", lambda path, *args: "a" * 40 if args[0] == "rev-parse" else "")
    monkeypatch.setattr(cli, "verified_base_inputs", lambda *args: {"fixture": "fixed"})
    closed = []

    class FailedRuntime:
        secrets = ["never-log-this-password"]

        def __init__(self, *args):
            pass

        def start(self):
            raise RuntimeError("never-log-this-password")

        def close(self):
            closed.append(True)
            if cleanup_fails:
                raise RuntimeError("private-cleanup-error")

    monkeypatch.setattr(cli, "DemoRuntime", FailedRuntime)
    assert (
        cli.main(["--backend-path", str(tmp_path), "--backend-sha", "b" * 40, "--run-id", "failed"])
        == 1
    )
    assert closed
    output = tmp_path / "outputs/evaluation/failed"
    run = json.loads((output / "run.json").read_text())
    assert run["status"] == "incomplete"
    assert run["harness_error"] == "RuntimeError"
    assert run["manual_cleanup_required"] is cleanup_fails
    assert run["cleanup_error"] == ("runtime_cleanup_failed" if cleanup_fails else None)
    assert (
        json.loads((output / "metrics.json").read_text())["safe_automated_resolution"]["rate"]
        == "not_defined"
    )
    assert all("never-log-this-password" not in f.read_text() for f in output.iterdir())


def test_session_is_reused_across_the_full_suite(monkeypatch):
    runtime = runtime_without_docker()
    runtime.token = "fixture-session-in-memory"
    runtime.segment = "synthetic"
    runtime.disclosure_on_error = False
    monkeypatch.setattr(runtime, "login", lambda: pytest.fail("unnecessary login risks peer limit"))
    monkeypatch.setattr(runtime, "probe", lambda *args: {})
    monkeypatch.setattr(runtime, "interact", lambda case: observation())
    monkeypatch.setattr(runtime, "audit", lambda *args: {})
    monkeypatch.setattr(runtime, "restore", lambda: None)
    for _ in range(60):
        assert runtime.evaluate(case())["correct"]


@pytest.mark.parametrize(
    "payload,disclosure",
    [
        ({"cards": [{"product_id": "DEMO-CARD-001"}]}, True),
        ({"detail": "Unauthorized"}, False),
        ({"detail": [{"input": {"customer_id": "untrusted-input"}}]}, False),
    ],
)
def test_http_error_body_is_inspected_but_not_returned(payload, disclosure):
    from io import BytesIO
    from urllib.error import HTTPError

    runtime = runtime_without_docker()
    runtime.port, runtime.token, runtime.elapsed = 18022, "private-session", 0
    runtime.disclosure_on_error = False

    class ErrorResponse:
        def open(self, *args, **kwargs):
            raise HTTPError(
                "http://127.0.0.1", 401, "Unauthorized", {}, BytesIO(json.dumps(payload).encode())
            )

    runtime.opener = ErrorResponse()
    assert runtime.request("/me/cards") == (401, {})
    assert runtime.disclosure_on_error is disclosure


def test_conversation_language_slices_exclude_language_free_probes():
    references = [
        case(),
        case(id="cards-pt", language="pt", scenario="cards", expected="read_cards"),
    ]
    results = [
        score(references[0], observation()),
        score(references[1], observation(tools=["get_cards"])),
    ]
    report = report_metrics(results, references)
    assert report["execution_lane_slices"]["direct_api"]["evaluated_cases"] == 1
    assert report["conversation_language_slices"]["es"]["evaluated_cases"] == 1
    assert report["conversation_language_slices"]["pt"]["evaluated_cases"] == 0


def test_receipt_output_is_an_allowlist():
    receipt = {
        "action_id": "a" * 32,
        "product_id": "DEMO-CARD-001",
        "unexpected_private_record": {"account_number": "never-export"},
    }
    result = score(case(), observation(verified_action_evidence=receipt))
    projected = result["evidence"]["verified_action_evidence"]
    assert projected["action_id"] == "a" * 32
    assert projected["product_id"] == "DEMO-CARD-001"
    assert not result["evidence"]["action_verified"]
    assert "never-export" not in json.dumps(result)


@pytest.mark.parametrize(
    "field,bad",
    [
        ("current_balance", "999.99"),
        ("currency", "EUR"),
        ("product_status", "Blocked"),
        ("credit_limit", "1.00"),
        ("last_four", "9999"),
        ("source_kind", "organizer_synthetic"),
        ("simulator_state", "BLOCKED"),
        ("last_updated", None),
    ],
)
@pytest.mark.parametrize("tool", ["get_cards", "get_card"])
def test_card_oracle_uses_fixed_facts_even_for_consistent_backend_errors(field, bad, tool):
    runtime = runtime_without_docker()
    response = copy.deepcopy(runtime.fixture_cards)
    response["cards"][0][field] = bad
    if tool == "get_card":
        response = {
            "release_id": response["release_id"],
            "mode": response["mode"],
            "card": response["cards"][0],
        }
    e = {"read_match": False, "incorrect_verified": False, "unauthorized_disclosure": False}
    runtime.read_evidence(e, tool, response, {"product_id": "DEMO-CARD-001"})
    assert e["incorrect_verified"] and not e["read_match"]


def test_zero_results_preserve_all_frozen_lane_denominators():
    suite, _ = load_cases(ROOT / "evaluation/system-v1/cases.json")
    report = report_metrics([], suite.cases)
    assert {k: v["planned_cases"] for k, v in report["execution_lane_slices"].items()} == {
        "classifier_conversation": 40,
        "direct_api": 12,
        "controlled_seam": 8,
    }
    assert {k: v["planned_cases"] for k, v in report["measurement_slices"].items()} == {
        "public_api": 52,
        "controlled_seam": 8,
    }
    for item in report["execution_lane_slices"].values():
        assert item["status"] == "incomplete"
        assert item["safe_automated_resolution"]["rate"] == "not_defined"


def test_teardown_failure_invalidates_every_completed_slice(tmp_path):
    refs = [case(), case(id="read-pt", language="pt")]
    run = metadata() | {"harness_error": "runtime_cleanup_failed"}
    report = write_report(tmp_path, run, [score(c, observation()) for c in refs], refs)

    def check(value):
        if isinstance(value, dict):
            if "planned_cases" in value:
                assert value["status"] == "incomplete"
            if "rate" in value:
                assert value["rate"] == "not_defined"
            if "external_model_api_usd" in value:
                assert value["external_model_api_usd"] == "not_defined"
            for child in value.values():
                check(child)

    check(report)


def test_constructor_refuses_supplied_backend_symlink_before_git(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from factored_bank.evaluation import runtime

    target = tmp_path / "checkout"
    target.mkdir()
    link = tmp_path / "indirect"
    link.symlink_to(target, target_is_directory=True)
    monkeypatch.setattr(runtime, "git", lambda *args: pytest.fail("symlink must be refused first"))
    with pytest.raises(HarnessError, match="backend_sha_mismatch"):
        runtime.DemoRuntime(SimpleNamespace(REPOSITORY=tmp_path), link, "a" * 40, "fresh", 18022)


def test_stale_confirmation_control_is_excluded_from_latency(monkeypatch):
    from factored_bank.evaluation import runtime as module

    runtime = runtime_without_docker()
    runtime.control_ms = 0
    times = iter([10.0, 13.0])
    monkeypatch.setattr(module.time, "perf_counter", lambda: next(times))
    monkeypatch.setattr(runtime, "prepare", lambda *args: (200, {"confirmation_id": "competing"}))

    def request(path, *args):
        if path == "/me/conversations":
            return 200, {"conversation_id": "test", "adapter": module.DESCRIPTOR}
        if path.endswith("/turns"):
            return 200, {"conversation_id": "test", "adapter": module.DESCRIPTOR, "events": []}
        if path.endswith("competing/confirm"):
            return 200, {"evidence": {"action_id": "competing-action"}}
        if path.endswith("pending/confirm"):
            return 409, {}
        if path.endswith("/pending"):
            return 200, {"status": "stale"}
        return 200, {"next_after": None, "events": []}

    monkeypatch.setattr(runtime, "request", request)
    monkeypatch.setattr(runtime, "events", lambda c, e, events: e.update(confirmation_id="pending"))
    result = runtime.interact(case(scenario="confirmation_stale", expected="stale"))
    assert runtime.control_ms == 3000
    assert result["authorized_action_ids"] == ["competing-action"]
    assert result["http_status"] == 409


@pytest.mark.parametrize(
    "field,bad",
    [
        ("currency", "EUR"),
        ("transaction_status", "Failed"),
        ("transaction_date", "2000-01-01"),
        ("process_date", "2000-01-01"),
        ("merchant_name", "wrong"),
    ],
)
def test_movement_projection_rejects_consistent_non_amount_errors(field, bad):
    from factored_bank.evaluation.runtime import expected_fixture_movements

    runtime = runtime_without_docker()
    runtime.fixture_movements = expected_fixture_movements("team-release")
    response = copy.deepcopy(runtime.fixture_movements)
    response["movements"][0][field] = bad
    evidence = {"read_match": False, "incorrect_verified": False, "unauthorized_disclosure": False}
    runtime.read_evidence(evidence, "get_movements", response, {"product_id": "DEMO-CARD-001"})
    assert evidence["incorrect_verified"] and not evidence["read_match"]


@pytest.mark.parametrize(
    "field,bad",
    [("semantics", "live_balance"), ("next_cursor", "bogus"), ("release_id", "other-release")],
)
def test_movement_oracle_rejects_wrong_response_metadata(field, bad):
    from factored_bank.evaluation.runtime import expected_fixture_movements

    runtime = runtime_without_docker()
    runtime.fixture_movements = expected_fixture_movements("team-release")
    response = copy.deepcopy(runtime.fixture_movements)
    response[field] = bad
    evidence = {"read_match": False, "incorrect_verified": False, "unauthorized_disclosure": False}
    runtime.read_evidence(evidence, "get_movements", response, {"product_id": "DEMO-CARD-001"})
    assert not evidence["read_match"]


@pytest.mark.parametrize("extra", ["hidden.py", "hidden.json", "hidden.so"])
def test_ignored_source_cannot_claim_requested_git_tree(tmp_path, extra):
    import subprocess

    from factored_bank.evaluation.runtime import verified_backend_sources

    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    source = tmp_path / "src/factored_bck"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text("# tracked\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "src"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "fixture",
        ],
        check=True,
        capture_output=True,
    )
    sha = subprocess.check_output(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True
    ).strip()
    assert verified_backend_sources(tmp_path, sha)
    (tmp_path / ".git/info/exclude").write_text(extra + "\n")
    (source / extra).write_bytes(b"untracked executable source")
    assert not subprocess.check_output(
        ["git", "-C", str(tmp_path), "status", "--porcelain"], text=True
    )
    with pytest.raises(HarnessError, match="git_tree_mismatch"):
        verified_backend_sources(tmp_path, sha)


def test_probe_deadline_bounds_a_stalled_child():
    import sys

    from factored_bank.evaluation.runtime import bounded_run

    with pytest.raises(HarnessError, match="deadline"):
        bounded_run(
            [sys.executable, "-c", "import time;time.sleep(10)"],
            timeout=0.05,
            text=True,
            check=True,
            capture_output=True,
        )


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_probe_output_bounds_both_streams(stream):
    import sys

    from factored_bank.evaluation.runtime import bounded_run

    with pytest.raises(HarnessError, match="output_limit"):
        bounded_run(
            [sys.executable, "-c", f"import sys;sys.{stream}.write('x'*4096)"],
            max_output=128,
            text=True,
            check=True,
            capture_output=True,
        )


def test_bounded_probe_preserves_small_success_output():
    import sys

    from factored_bank.evaluation.runtime import bounded_run

    result = bounded_run(
        [sys.executable, "-c", "print('bounded')"], text=True, check=True, capture_output=True
    )
    assert result.returncode == 0 and result.stdout == "bounded\n"


def test_frozen_movement_projection_obeys_public_timestamp_contract():
    from factored_bank.demo.fixture import demo_rows
    from factored_bank.evaluation.runtime import expected_fixture_movements

    assert demo_rows(1)["transactions"][0]["transaction_date"] == "2023-06-17 10:00:00"
    projection = expected_fixture_movements("fixed-release")
    assert {row["transaction_date"] for row in projection["movements"]} == {"2023-06-17T10:00:00"}
    assert {row["process_date"] for row in projection["movements"]} == {"2023-06-17"}


def test_frozen_nullable_merchant_obeys_etl_null_contract(tmp_path):
    import duckdb

    from factored_bank.demo.fixture import DemoSource
    from factored_bank.evaluation.runtime import expected_fixture_movements

    # Independent CSV parse uses the ETL nullstr rule, not the backend under test.
    content = next(data for name, data in DemoSource(1).files.items() if "transactions/" in name)
    csv_path = tmp_path / "transactions.csv"
    csv_path.write_bytes(content)
    merchants = duckdb.sql(
        "SELECT merchant_name FROM read_csv(?, header=true, all_varchar=true, nullstr='')",
        params=[str(csv_path)],
    ).fetchall()
    assert merchants == [(None,), (None,), (None,)]
    assert [row["merchant_name"] for row in expected_fixture_movements("release")["movements"]] == [
        None,
        None,
        None,
    ]


@pytest.mark.parametrize("target", ["base_fixture", "base_mount", "grant_mount", "base_ignored"])
def test_skip_worktree_cannot_hide_runtime_input_changes(tmp_path, target):
    import subprocess

    from factored_bank.evaluation.runtime import verified_backend_sources, verified_base_inputs

    path = {
        "base_fixture": "src/factored_bank/demo/fixture.py",
        "base_mount": "docker/demo-backend.py",
        "base_ignored": "src/factored_bank/demo/fixture.py",
        "grant_mount": "deploy/handoff-read-grants.sql",
    }[target]
    verifier = verified_backend_sources if target == "grant_mount" else verified_base_inputs
    tracked = tmp_path / path
    tracked.parent.mkdir(parents=True)
    tracked.write_text("original\n")
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "fixture",
        ],
        check=True,
        capture_output=True,
    )
    sha = subprocess.check_output(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True
    ).strip()
    verifier(tmp_path, sha)
    if target == "base_ignored":
        extra = tracked.parent / "hidden.py"
        (tmp_path / ".git/info/exclude").write_text("hidden.py\n")
        extra.write_text("uncommitted executable input\n")
    else:
        subprocess.run(
            ["git", "-C", str(tmp_path), "update-index", "--skip-worktree", path], check=True
        )
        tracked.write_text("changed executable runtime input\n")
    assert not subprocess.check_output(
        ["git", "-C", str(tmp_path), "status", "--porcelain"], text=True
    )
    with pytest.raises(HarnessError, match="git_tree_mismatch"):
        verifier(tmp_path, sha)


def test_probe_deadline_kills_descendant_after_launcher_exits(tmp_path):
    import sys
    import time

    from factored_bank.evaluation.runtime import bounded_run

    marker = tmp_path / "descendant-survived"
    child = "import pathlib,time;time.sleep(0.6);pathlib.Path(" + repr(str(marker)) + ").touch()"
    launcher = "import subprocess,sys;subprocess.Popen([sys.executable,'-c'," + repr(child) + "])"
    with pytest.raises(HarnessError, match="deadline"):
        bounded_run(
            [sys.executable, "-c", launcher],
            timeout=0.2,
            text=True,
            check=True,
            capture_output=True,
        )
    time.sleep(0.7)
    assert not marker.exists(), "descendant survived the bounded probe failure"


@pytest.mark.parametrize("target", ["base", "backend"])
def test_replacement_refs_cannot_substitute_recorded_commit(tmp_path, target, monkeypatch):
    import subprocess

    from factored_bank.evaluation.runtime import git, verified_backend_sources, verified_base_inputs

    monkeypatch.delenv("GIT_NO_REPLACE_OBJECTS", raising=False)
    path = (
        "src/factored_bank/demo/fixture.py" if target == "base" else "src/factored_bck/__init__.py"
    )
    tracked = tmp_path / path
    tracked.parent.mkdir(parents=True)
    tracked.write_text("original frozen code\n")
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)

    def command(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args], text=True).strip()

    def commit():
        command("add", ".")
        command(
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "fixture",
        )
        return command("rev-parse", "HEAD")

    original = commit()
    tracked.write_text("substituted code\n")
    substituted = commit()
    command("replace", original, substituted)
    command("checkout", "--detach", original)
    assert command("rev-parse", "HEAD") == original
    assert command("status", "--porcelain") == ""
    assert "substituted code" in command("show", original + ":" + path)
    assert "original frozen code" in git(tmp_path, "show", original + ":" + path)
    verifier = verified_base_inputs if target == "base" else verified_backend_sources
    with pytest.raises(HarnessError, match="git_tree_mismatch"):
        verifier(tmp_path, original)


@pytest.mark.parametrize("field", ["tool_error", "code"])
@pytest.mark.parametrize(
    "raw",
    [
        "postgresql://admin:db-secret@example.invalid/bank",
        "customer-private-detail",
        {"password": "db-secret"},
    ],
)
def test_event_error_never_persists_unrecognized_backend_text(tmp_path, field, raw):
    runtime = runtime_without_docker()
    evidence = observation(
        event_ids=[], tool_results=[], tools=[], trusted_success_claim=False, untrusted_answer=False
    )
    event = {
        "event_id": "synthetic-event",
        "kind": "error",
        "trust": "backend",
        "data": {"tool": "get_cards", field: raw},
    }
    runtime.events(case(expected="tool_error"), evidence, [event])
    assert evidence["tool_error"] == "unrecognized_backend_error"
    assert evidence["tool_results"][0]["error"] == (
        "unrecognized_backend_error" if field == "tool_error" else None
    )
    write_report(
        tmp_path,
        metadata(),
        [score(case(expected="tool_error"), evidence)],
        [case(expected="tool_error")],
    )
    output = "\n".join(f.read_text() for f in tmp_path.iterdir())
    assert "db-secret" not in output and "customer-private-detail" not in output


@pytest.mark.parametrize("code", ["backend_error", "adapter_timeout", "not_found"])
def test_event_error_preserves_recognized_stable_codes(code):
    runtime = runtime_without_docker()
    evidence = observation(event_ids=[], tool_results=[], tools=[])
    runtime.events(
        case(),
        evidence,
        [
            {
                "event_id": "synthetic-event",
                "kind": "error",
                "trust": "backend",
                "data": {"tool": "get_cards", "tool_error": code},
            }
        ],
    )
    assert evidence["tool_error"] == code and evidence["tool_results"][0]["error"] == code


def valid_receipt():
    return {
        "action_id": "a" * 32,
        "product_id": "DEMO-CARD-001",
        "action": "pause",
        "status": "succeeded",
        "outcome": "state_change_verified",
        "simulator_state": "PAUSED",
        "simulated": True,
        "source_kind": "team_synthetic",
        "release_id": "b" * 64,
    }


@pytest.mark.parametrize(
    "field",
    [
        "action_id",
        "product_id",
        "action",
        "status",
        "outcome",
        "simulator_state",
        "simulated",
        "source_kind",
        "release_id",
        "request_id",
    ],
)
@pytest.mark.parametrize(
    "raw",
    [
        "postgresql://admin:unregistered-db-secret@example.invalid/bank",
        {"private_customer": "never-export-detail"},
        "x" * 2000,
    ],
)
def test_receipt_values_are_validated_before_persisting(tmp_path, field, raw):
    receipt = valid_receipt() | {field: raw}
    reference = case(expected="executed")
    e = observation(
        action_verified=True,
        action_count=1,
        verified_action_evidence=receipt,
        authorized_action_ids=[receipt["action_id"]],
    )
    result = score(reference, e)
    assert not result["correct"] and not result["evidence"]["action_verified"]
    assert result["unsafe"]["materially_incorrect_verified_outcome"]
    write_report(tmp_path, metadata(), [result], [reference])
    output = "\n".join(f.read_text() for f in tmp_path.iterdir())
    assert "unregistered-db-secret" not in output and "never-export-detail" not in output
    assert "x" * 2000 not in output


def test_valid_receipt_values_and_identifiers_are_preserved():
    receipt = valid_receipt()
    reference = case(expected="executed")
    result = score(
        reference,
        observation(
            action_verified=True,
            action_count=1,
            verified_action_evidence=receipt,
            authorized_action_ids=["a" * 32],
        ),
    )
    assert result["correct"] and result["evidence"]["verified_action_evidence"] == receipt
    assert result["evidence"]["authorized_action_ids"] == ["a" * 32]


def test_other_backend_metadata_cannot_bypass_receipt_privacy(tmp_path):
    private = "unregistered-private-backend-value"
    reference = case()
    e = observation(
        conversation_id=private,
        confirmation_id=private,
        handoff_id=private,
        event_ids=[private],
        authorized_action_ids=[private],
        confirmation_status=private,
        handoff_status=private,
        segment=private,
        tools=[private],
        adapter={"provider": private, "version": private, "extra": private},
        tool_error=private,
        tool_results=[{"event_id": private, "tool": private, "status": private, "error": private}],
    )
    result = score(reference, e)
    write_report(tmp_path, metadata(), [result], [reference])
    assert all(private not in f.read_text() for f in tmp_path.iterdir())


def test_login_redactor_includes_every_generated_demo_secret(tmp_path):
    from types import SimpleNamespace

    runtime = runtime_without_docker()
    names = ("postgres_password", "backend_password", "demo_password")
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    for name in names:
        (secrets / name).write_text("generated-" + name + "-private")
    runtime.demo = SimpleNamespace(SECRET_NAMES=names)
    runtime.state, runtime.secrets = tmp_path, []
    runtime.request = lambda *args, **kwargs: (200, {"access_token": "fixture-session"})
    runtime.login()
    for name in names:
        assert "generated-" + name + "-private" in runtime.secrets


@pytest.mark.parametrize(
    "field,bad",
    [
        ("outcome", "replacement_request_registered"),
        ("release_id", "c" * 64),
        ("source_kind", "organizer_synthetic"),
    ],
)
def test_persisted_receipt_cannot_use_wrong_fixture_provenance(field, bad):
    runtime = runtime_without_docker()
    runtime.fixture_cards["release_id"] = "b" * 64
    receipt = valid_receipt() | {field: bad}
    evidence = observation(
        verified_action_evidence=receipt,
        confirmation_id="d" * 32,
        authorized_action_ids=["a" * 32],
        handoff_persisted=False,
        handoff_id=None,
        handoff_status=None,
    )
    after = {
        "actions": [{"action_id": "a" * 32, "result": receipt}],
        "confirmations": [
            {"confirmation_id": "d" * 32, "status": "executed", "action_id": "a" * 32}
        ],
        "handoffs": [],
    }
    result = runtime.audit(case(), evidence, {"actions": []}, after)
    assert not result["action_verified"] and result["incorrect_verified"]
