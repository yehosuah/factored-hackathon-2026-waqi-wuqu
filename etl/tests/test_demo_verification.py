"""Proof failures must not leave the regular ETL scheduler stopped."""

import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest


@pytest.fixture
def verification(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "demo_verification", Path(__file__).parents[1] / "scripts/verify_demo.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "defect", [None, "wrong_tool", "wrong_card", "wrong_release", "wrong_rows", "untrusted"]
)
def test_classifier_proof_rejects_unrelated_or_incorrect_movement_result(verification, defect):
    expected = {
        "release_id": "synthetic-release",
        "semantics": "historical_source_movements",
        "movements": [{"transaction_id": f"synthetic-{n}", "amount": n} for n in range(3)],
        "next_cursor": None,
    }
    event = {
        "kind": "tool_result",
        "trust": "backend",
        "data": {
            "tool": "get_movements",
            "arguments": {"product_id": "DEMO-CARD-001"},
            "result": deepcopy(expected),
        },
    }
    if defect == "wrong_tool":
        event["data"]["tool"] = "get_cards"
    elif defect == "wrong_card":
        event["data"]["arguments"]["product_id"] = "DEMO-CARD-OTHER"
    elif defect == "wrong_release":
        event["data"]["result"]["release_id"] = "stale-release"
    elif defect == "wrong_rows":
        event["data"]["result"]["movements"][0]["amount"] = 999
    elif defect == "untrusted":
        event["trust"] = "untrusted"
    if defect:
        with pytest.raises(AssertionError):
            verification.assert_movement_turn({"events": [event]}, expected)
    else:
        verification.assert_movement_turn({"events": [event]}, expected)


@pytest.mark.parametrize("failure", [False, True])
def test_manual_proof_excludes_scheduler_and_resumes_after_failure(
    monkeypatch, verification, failure
):
    module = verification
    running = True

    def control(state, settings, operation, *arguments, **kwargs):
        nonlocal running
        assert arguments[-1] == "etl"
        if operation == "stop":
            assert running
            running = False
        elif operation == "start":
            assert not running
            running = True
        else:
            raise AssertionError("Unexpected scheduler operation")

    monkeypatch.setattr(module, "compose", control)
    try:
        with module.manual_etl_window(None, None):
            assert not running
            if failure:
                raise RuntimeError("synthetic_proof_failure")
    except RuntimeError:
        assert failure
    assert running
