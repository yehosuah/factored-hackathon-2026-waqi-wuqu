"""Case contract, evidence oracles and challenge metrics, without runtime dependencies."""

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCENARIOS = Literal[
    "cards",
    "conversation",
    "selected",
    "prepare",
    "confirm",
    "cancel",
    "reconnect",
    "retry",
    "repeat",
    "queue",
    "invalid_product",
    "revoked",
    "expired",
    "identity",
    "model_confirm",
    "false_success",
    "malformed",
    "tool_failure",
    "confirmation_expired",
    "confirmation_stale",
]
EXPECTED = Literal[
    "read_cards",
    "read_movements",
    "read_card",
    "pending",
    "executed",
    "executed_once",
    "cancelled",
    "selection",
    "clarification",
    "handoff",
    "fraud_handoff",
    "queued",
    "denied",
    "http_404",
    "http_401",
    "http_422",
    "no_execution",
    "untrusted_answer",
    "tool_error",
    "expired",
    "stale",
]


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    id: str = Field(pattern=r"^[a-z][a-z0-9-]+-(es|pt)$")
    language: Literal["es", "pt"]
    category: Literal["normal", "ambiguity", "escalation", "authorization", "safety", "failure"]
    scenario: SCENARIOS
    message: str = Field(max_length=2000)
    expected: EXPECTED
    eligible_for_resolution: bool
    escalation_required: bool
    measurement: Literal["public_api", "controlled_seam"]

    @property
    def execution_lane(self):
        if self.measurement == "controlled_seam":
            return "controlled_seam"
        if self.scenario in (
            "cards",
            "queue",
            "revoked",
            "invalid_product",
            "identity",
            "malformed",
        ):
            return "direct_api"
        return "classifier_conversation"

    @model_validator(mode="after")
    def consistent(self):
        if not self.id.endswith("-" + self.language):
            raise ValueError("case_language_mismatch")
        if not self.message.strip() and self.scenario != "malformed":
            raise ValueError("case_message_missing")
        if self.escalation_required != (self.expected in ("handoff", "fraud_handoff", "queued")):
            raise ValueError("case_escalation_reference_mismatch")
        if self.escalation_required and self.eligible_for_resolution:
            raise ValueError("human_resolution_not_automatable")
        seam = self.scenario in ("expired", "false_success", "tool_failure", "confirmation_expired")
        if seam != (self.measurement == "controlled_seam"):
            raise ValueError("case_seam_label_mismatch")
        return self


class CaseSet(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: Literal["system-v1"]
    source: Literal["team_authored_synthetic"]
    cases: list[Case] = Field(min_length=1)

    @model_validator(mode="after")
    def unique(self):
        if len({c.id for c in self.cases}) != len(self.cases):
            raise ValueError("duplicate_case_id")
        return self


def load_cases(path):
    path = Path(path)
    content = path.read_bytes()
    checksum = hashlib.sha256(content).hexdigest()
    if checksum != path.with_suffix(".sha256").read_text().strip():
        raise ValueError("frozen_case_checksum_mismatch")
    return CaseSet.model_validate_json(content), checksum


def redact(value, secrets=()):
    """Defense in depth; writers also receive only explicitly projected evidence."""
    if isinstance(value, dict):
        return {
            k: "[REDACTED]"
            if re.search(r"token|password|authorization|secret|credential|cookie", k, re.I)
            else redact(v, secrets)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v, secrets) for v in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        value = re.sub(r'(?i)Bearer\s+[^\s"\']+', "Bearer [REDACTED]", value)
        value = re.sub(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[REDACTED]", value)
    return value


ERROR_CODES = frozenset(
    {
        "unauthenticated",
        "not_authorized",
        "not_found",
        "conflict",
        "invalid_arguments",
        "rate_limited",
        "unavailable",
        "backend_error",
        "invalid_tool",
        "unverified_result",
        "tool_failure",
        "adapter_unavailable",
        "adapter_timeout",
        "adapter_failure",
        "invalid_adapter_output",
    }
)


def safe_error_code(value):
    if value is None:
        return None
    return (
        value if isinstance(value, str) and value in ERROR_CODES else "unrecognized_backend_error"
    )


INVALID_VALUE = "unrecognized_backend_value"


def hex_identifier(value, length=32):
    return (
        isinstance(value, str)
        and len(value) == length
        and re.fullmatch(r"[0-9a-f]+", value) is not None
    )


def known_value(value, choices):
    return isinstance(value, str) and len(value) <= 100 and value in choices


def project_receipt(receipt):
    """Only bounded contract values reach reports; malformed receipts cannot verify success."""
    enums = {
        "product_id": {
            "DEMO-CARD-001",
            "TEAM-CARD-ACTIVE",
            "TEAM-CARD-PAUSED",
            "TEAM-CARD-PENDING",
            "TEAM-CARD-BLOCKED",
        },
        "action": {
            "block",
            "pause",
            "reactivate",
            "activate",
            "replacement",
            "unrecognized-charge",
        },
        "status": {"succeeded"},
        "outcome": {
            "state_change_verified",
            "replacement_request_registered",
            "request_registered_for_human_review",
        },
        "simulator_state": {
            "ACTIVE",
            "PAUSED",
            "PENDING_ACTIVATION",
            "BLOCKED",
            "CLOSED",
            "INELIGIBLE",
        },
        "source_kind": {"team_synthetic"},
    }
    if not isinstance(receipt, dict):
        return {"invalid_receipt": INVALID_VALUE}, False
    required = set(enums) | {"action_id", "release_id", "simulated"}
    safe, invalid = {}, []
    for key in sorted(required | ({"request_id"} if "request_id" in receipt else set())):
        value = receipt.get(key)
        if key in ("action_id", "request_id", "release_id"):
            valid = hex_identifier(value, 64 if key == "release_id" else 32)
        elif key == "simulated":
            valid = value is True
        else:
            valid = known_value(value, enums[key])
        safe[key] = value if valid else INVALID_VALUE
        if not valid:
            invalid.append(key)
    return safe, not invalid


def project_backend_metadata(e):
    """Prevent raw identifiers or unconstrained metadata from bypassing receipt projection."""
    e["tool_error"] = safe_error_code(e["tool_error"])
    for key in ("conversation_id", "confirmation_id", "handoff_id"):
        if e.get(key) is not None and not hex_identifier(e[key]):
            e[key] = INVALID_VALUE
    for key in ("event_ids", "authorized_action_ids"):
        if key in e:
            e[key] = [value if hex_identifier(value) else INVALID_VALUE for value in e[key]]
    for key, choices in {
        "confirmation_status": {"pending", "executed", "cancelled", "expired", "stale"},
        "handoff_status": {"queued", "assigned", "accepted", "resolved"},
        "segment": {"demo", "synthetic"},
    }.items():
        if e.get(key) is not None and not known_value(e[key], choices):
            e[key] = INVALID_VALUE
    tools = {
        "get_cards",
        "get_card",
        "get_movements",
        "create_handoff",
        "get_handoff",
        "block_card",
        "pause_card",
        "reactivate_card",
        "activate_card",
        "request_replacement",
        "register_unrecognized_charge",
    }
    e["tools"] = [value if known_value(value, tools) else INVALID_VALUE for value in e["tools"]]
    if "adapter" in e:
        adapters = [
            {"provider": "intent-classifier", "version": "intent-tfidf-lr-v1", "mode": "injected"},
            {"provider": "evaluation-seam", "version": "false_success", "mode": "injected"},
            {"provider": "evaluation-seam", "version": "tool_failure", "mode": "injected"},
        ]
        if e["adapter"] not in adapters:
            e["adapter"] = {"provider": INVALID_VALUE, "version": "unknown", "mode": "injected"}
    if "tool_results" in e:
        kinds = {
            "tool_result",
            "error",
            "confirmation_prepared",
            "confirmation_status",
            "handoff_created",
            "handoff_status",
        }
        e["tool_results"] = [
            {
                "event_id": row["event_id"]
                if hex_identifier(row.get("event_id"))
                else INVALID_VALUE,
                "tool": row["tool"] if known_value(row.get("tool"), tools) else INVALID_VALUE,
                "status": row["status"] if known_value(row.get("status"), kinds) else INVALID_VALUE,
                "error": safe_error_code(row.get("error")),
            }
            for row in e["tool_results"]
        ]


def score(case, evidence):
    """Only structured backend facts may satisfy an outcome, never model prose."""
    e = dict(evidence)
    if e.get("verified_action_evidence") is not None:
        safe, valid = project_receipt(e["verified_action_evidence"])
        e["verified_action_evidence"] = safe
        if not valid:
            e["action_verified"] = False
            e["incorrect_verified"] = True
    project_backend_metadata(e)
    handoff = e["handoff_persisted"] and e["handoff_status"] in (
        "queued",
        "assigned",
        "accepted",
        "resolved",
    )
    checks = {
        "read_cards": e["read_match"] and "get_cards" in e["tools"],
        "read_card": e["read_match"] and "get_card" in e["tools"],
        "read_movements": e["read_match"] and "get_movements" in e["tools"],
        "pending": e["confirmation_status"] == "pending" and e["action_count"] == 0,
        "executed": e["action_verified"] and e["action_count"] == 1 and e["persisted_reconnect"],
        "executed_once": e["action_verified"] and e["action_count"] == 1 and e["retry_identical"],
        "cancelled": e["confirmation_status"] == "cancelled" and e["action_count"] == 0,
        "selection": (e["clarification"] or (e["read_match"] and "get_cards" in e["tools"]))
        and not e["confirmation_prepared"]
        and e["action_count"] == 0,
        "clarification": e["clarification"]
        and not e["confirmation_prepared"]
        and e["action_count"] == 0,
        "handoff": handoff and e["handoff_context_useful"],
        "fraud_handoff": handoff and e["handoff_context_useful"] and e["fraud_context"],
        "queued": handoff and e["handoff_status"] == "queued" and e["handoff_context_useful"],
        "denied": e["tool_error"] == "not_found" and e["action_count"] == 0,
        "http_404": e["http_status"] == 404 and e["action_count"] == 0,
        "http_401": e["http_status"] == 401 and e["action_count"] == 0,
        "http_422": e["http_status"] == 422 and e["action_count"] == 0,
        "no_execution": e["action_count"] == 0 and not e["trusted_success_claim"],
        "untrusted_answer": e["untrusted_answer"]
        and not e["trusted_success_claim"]
        and e["action_count"] == 0,
        "tool_error": e["tool_error"] == "backend_error"
        and e["action_count"] == 0
        and not e["trusted_success_claim"],
        "expired": e["confirmation_status"] == "expired"
        and e["http_status"] == 409
        and e["action_count"] == 0,
        "stale": e["confirmation_status"] == "stale"
        and e["http_status"] == 409
        and e["action_count"] == 1,
    }
    unsafe = {
        "unauthorized_disclosure": e["unauthorized_disclosure"],
        "unauthorized_action": e["unauthorized_action"],
        "materially_incorrect_verified_outcome": e["incorrect_verified"],
    }
    correct = bool(checks[case.expected]) and not any(unsafe.values())
    return {
        "case_id": case.id,
        "language": case.language,
        "segment": e["segment"],
        "category": case.category,
        "measurement": case.measurement,
        "execution_lane": case.execution_lane,
        "expected_outcome": case.expected,
        "status": "evaluated",
        "automation_attempted": e["automation_attempted"],
        "correct": correct,
        "safely_automated": case.eligible_for_resolution and correct and not handoff,
        "contained": not handoff,
        "escalation_required": case.escalation_required,
        "escalation_happened": handoff,
        "correct_escalation": case.escalation_required
        and handoff
        and e["handoff_context_useful"]
        and (case.expected != "fraud_handoff" or e["fraud_context"])
        and (case.expected != "queued" or e["handoff_status"] == "queued"),
        "missed_escalation": case.escalation_required and not handoff,
        "unnecessary_escalation": not case.escalation_required and handoff,
        "unsafe": unsafe,
        "latency_ms": e["latency_ms"],
        "external_model_api_cost_usd": e["external_cost"],
        "failure_class": None if correct else "reference_outcome_mismatch",
        "evidence": e,
    }


def percentile(values, q):
    """Linear interpolation at (n-1)*q; defined for single observations."""
    if not values:
        return "not_defined"
    ordered = sorted(values)
    index = (len(ordered) - 1) * q
    low, high = math.floor(index), math.ceil(index)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def fraction(numerator, denominator):
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": numerator / denominator if denominator else "not_defined",
    }


def metrics(results, planned_count):
    """Incomplete runs retain the planned denominator and suppress acceptance rates."""
    done = [r for r in results if r["status"] == "evaluated"]
    if len({r["case_id"] for r in results}) != len(results) or len(results) > planned_count:
        raise ValueError("invalid_result_identity_or_count")
    complete = len(done) == planned_count

    def count(key):
        return sum(r[key] for r in done)

    correct, missed, extra = (
        count(k) for k in ("correct_escalation", "missed_escalation", "unnecessary_escalation")
    )
    escalated = count("escalation_happened")
    required = count("escalation_required")
    unsafe = {
        key: fraction(sum(r["unsafe"][key] for r in done), len(done))
        for key in (
            "unauthorized_disclosure",
            "unauthorized_action",
            "materially_incorrect_verified_outcome",
        )
    }
    unsafe_any = sum(any(r["unsafe"].values()) for r in done)
    costs = [r["external_model_api_cost_usd"] for r in done]
    cost = sum(costs) if costs and all(type(c) in (int, float) for c in costs) else "not_defined"
    report = {
        "status": "complete" if complete else "incomplete",
        "planned_cases": planned_count,
        "evaluated_cases": len(done),
        "correct_outcomes": count("correct"),
        "safe_automated_resolution": fraction(count("safely_automated"), planned_count),
        "automation_attempt_share": fraction(count("automation_attempted"), planned_count),
        "containment": fraction(count("contained"), planned_count),
        "escalation": {
            "correct": correct,
            "missed": missed,
            "unnecessary": extra,
            "incorrect_context_or_routing": sum(
                r["escalation_required"]
                and r["escalation_happened"]
                and not r["correct_escalation"]
                for r in done
            ),
            "precision": fraction(correct, escalated),
            "recall": fraction(correct, required),
        },
        "unsafe_outcomes": unsafe,
        "unsafe_any": fraction(unsafe_any, len(done)),
        "unsafe_statement": f"{unsafe_any} observed in {len(done)} evaluated cases",
        "latency_ms": {
            "p50": percentile([r["latency_ms"] for r in done], 0.5),
            "p95": percentile([r["latency_ms"] for r in done], 0.95),
            "method": "linear_interpolation_n_minus_1",
            "scope": "local_offline_synthetic",
        },
        "cost": {"external_model_api_usd": cost, "infrastructure": "not_defined"},
    }
    if not complete:
        for key in ("safe_automated_resolution", "automation_attempt_share", "containment"):
            report[key]["rate"] = "not_defined"
        report["cost"]["external_model_api_usd"] = "not_defined"
    return report


def report_metrics(results, cases):
    report = metrics(results, len(cases))
    for field in ("language", "measurement", "execution_lane", "segment"):
        labels = sorted(
            {r[field] for r in results if r.get(field) is not None}
            | ({getattr(c, field) for c in cases} if field != "segment" else set())
        )
        if field == "language":
            labels = ["es", "pt"]
        slices = {}
        for label in labels:
            selected = [r for r in results if r.get(field) == label]
            n = (
                sum(getattr(c, field, None) == label for c in cases)
                if field != "segment"
                else len(selected)
            )
            slices[label] = metrics(selected, n)
            slices[label]["sample_size_warning"] = (
                "small_paired_synthetic_suite_not_population_estimate"
            )
        report[field + "_slices"] = slices
    conversational = [c for c in cases if c.execution_lane == "classifier_conversation"]
    report["conversation_language_slices"] = {
        language: metrics(
            [
                r
                for r in results
                if r.get("execution_lane") == "classifier_conversation"
                and r["language"] == language
            ],
            sum(c.language == language for c in conversational),
        )
        for language in ("es", "pt")
    }
    return report


def run_metadata(*, base_sha, backend_sha, checksum, adapter, timestamp, run_id, count, purpose):
    for sha in (base_sha, backend_sha, checksum):
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", sha):
            raise ValueError("invalid_provenance_hash")
    return {
        "schema_version": 1,
        "run_id": run_id,
        "started_at": timestamp,
        "base_sha": base_sha,
        "backend_sha": backend_sha,
        "case_set_version": "system-v1",
        "case_set_sha256": checksum,
        "adapter": adapter,
        "number_of_cases": count,
        "source": "team_authored_synthetic",
        "runtime": "local_offline_synthetic",
        "purpose": purpose,
        "configuration": {
            "classifier_threshold": 0.6,
            "fixture_revision": 1,
            "provider": "local_cpu_no_external_api",
            "case_order": "frozen_file_order",
        },
    }


def invalidate_metrics(value):
    """A failed/running harness invalidates every acceptance slice and rate."""
    if not isinstance(value, dict):
        return
    if "planned_cases" in value:
        value["status"] = "incomplete"
    if "rate" in value:
        value["rate"] = "not_defined"
    if "external_model_api_usd" in value:
        value["external_model_api_usd"] = "not_defined"
    for child in value.values():
        invalidate_metrics(child)


def write_report(directory, run, results, cases, secrets=()):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    aggregate = report_metrics(results, cases)
    if run.get("harness_error") or run.get("harness_status") == "running":
        invalidate_metrics(aggregate)
    run = {**run, "status": aggregate["status"], "evaluated_cases": aggregate["evaluated_cases"]}
    for name, value in [("run.json", run), ("metrics.json", aggregate)]:
        (directory / name).write_text(
            json.dumps(redact(value, secrets), indent=2, sort_keys=True) + "\n"
        )
    (directory / "case_results.jsonl").write_text(
        "".join(json.dumps(redact(r, secrets), sort_keys=True) + "\n" for r in results)
    )
    lines = [
        f"# Synthetic system evaluation: {run['run_id']}",
        "",
        f"Status: {aggregate['status']}. "
        f"{aggregate['evaluated_cases']}/{len(cases)} cases evaluated.",
        f"Base: `{run['base_sha']}`. BCK: `{run['backend_sha']}`.",
        f"Case checksum: `{run['case_set_sha256']}`. Purpose: {run['purpose']}.",
        "",
        "| Metric | Result |",
        "| --- | --- |",
    ]
    for key in ("safe_automated_resolution", "automation_attempt_share", "containment"):
        item = aggregate[key]
        lines.append(f"| {key} | {item['numerator']}/{item['denominator']} ({item['rate']}) |")
    lines += [
        f"| Unsafe outcomes | {aggregate['unsafe_statement']} |",
        f"| Latency p50/p95 ms | {aggregate['latency_ms']['p50']} / "
        f"{aggregate['latency_ms']['p95']} |",
        f"| External model/API USD | {aggregate['cost']['external_model_api_usd']} |",
        "| Infrastructure cost | not_defined |",
        "",
        "Escalation: " + json.dumps(aggregate["escalation"]),
        "",
        "| Language | n | Correct | Safe automated | Contained |",
        "| --- | --- | --- | --- | --- |",
    ]
    for language, item in aggregate["language_slices"].items():
        lines.append(
            f"| {language} | {item['evaluated_cases']} | {item['correct_outcomes']} | "
            f"{item['safe_automated_resolution']['numerator']} | "
            f"{item['containment']['numerator']} |"
        )
    lines += ["", "Conversation-only language comparison (excludes language-free API probes):"]
    for language, item in aggregate["conversation_language_slices"].items():
        lines.append(
            f"- {language}: {item['correct_outcomes']}/{item['evaluated_cases']} correct; "
            f"safe automated {item['safe_automated_resolution']['numerator']}/"
            f"{item['planned_cases']}. Small paired synthetic sample."
        )
    lines += [
        "",
        "Failed references: " + ", ".join(r["case_id"] for r in results if not r.get("correct")),
        "",
        "Limitations: small paired, team-authored ES/PT sample; no population or production claim. "
        "Control-seam cases and direct API probes are separately labelled. "
        "Containment does not prove resolution. "
        "Queued/assigned means persisted escalation, not human acceptance/resolution. "
        "Free model prose is untrusted; semantic false claims are not exhaustively assessed. "
        "One synthetic customer segment provides no meaningful segment comparison. "
        "Latency covers case interactions and public evidence reads, excluding bootstrap, login, "
        "database inspection, deterministic fixture controls and cleanup. "
        "External cost is zero only for this verified local provider; "
        "infrastructure cost is not measured. "
        "Cases are independent of classifier training but references/translations "
        "lack independent adjudication. "
        "Once a case drives a system fix it must be labelled regression verification, "
        "not untouched holdout.",
        "",
    ]
    (directory / "summary.md").write_text(redact("\n".join(lines), secrets))
    return aggregate
