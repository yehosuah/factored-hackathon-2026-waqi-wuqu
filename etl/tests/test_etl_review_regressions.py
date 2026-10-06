"""Review regressions using only invented team fixtures."""

import json
from pathlib import Path

import pytest
from etl_fixtures import raw_release, rows

from factored_bank.etl.transform import prepare
from factored_bank.extract.inventory import scope_definition
from factored_bank.extract.pipeline import release_identity


def test_pilot_scope_is_rejected_before_cached_release_reuse(tmp_path):
    manifest, raw = raw_release(tmp_path)
    output = tmp_path / "processed"
    accepted, original = prepare(manifest, raw, output)
    candidate = json.loads(Path(manifest).read_text())
    candidate["scope_id"], candidate["scope"] = scope_definition(
        candidate["source"], "pilot", "2023-06-17"
    )
    candidate["release_id"] = release_identity(candidate)
    pilot = tmp_path / "pilot.json"
    pilot.write_text(json.dumps(candidate))
    assert len({o["table"] for o in candidate["objects"]}) == 9
    with pytest.raises(ValueError, match="incomplete_raw_scope"):
        prepare(pilot, raw, output)
    assert list((output / "releases").iterdir()) == [accepted]
    assert not (output / "current.json").exists()
    assert original["tables"]["transactions"]["accepted"] == 1


@pytest.mark.parametrize("parent_state", ["missing", "quarantined", "different_customer"])
def test_interaction_parent_requires_same_process_date_and_customer(tmp_path, parent_state):
    data = rows()
    day = "2023-06-18"
    children = ["call_transcripts", "satisfaction_surveys", "complaints"]
    extra = [(table, day, [{**data[table][0], "process_date": day}]) for table in children]
    if parent_state != "missing":
        parent = {**data["call_center_interactions"][0], "process_date": day}
        if parent_state == "quarantined":
            parent["interaction_type"] = ""
        else:
            customer = {**data["customers"][0], "customer_id": "customers-2"}
            customer["document_number"] = "TEAM-DOC-002"
            data["customers"].append(customer)
            parent["customer_id"] = customer["customer_id"]
        extra.append(("call_center_interactions", day, [parent]))
    manifest, raw = raw_release(tmp_path, data, extra)
    _, result = prepare(manifest, raw, tmp_path / "processed")
    for table in children:
        counts = result["tables"][table]
        assert (counts["input"], counts["accepted"], counts["rejected"]) == (2, 1, 1)
        reason = (
            "interaction_customer_mismatch"
            if parent_state == "different_customer"
            else "unresolved_reference:"
            + ("origin_interaction_id" if table == "complaints" else "interaction_id")
        )
        assert counts["reasons"][reason] == 1


def test_same_interaction_id_on_two_dates_preserves_matching_children(tmp_path):
    data = rows()
    tables = ["call_center_interactions", "call_transcripts", "satisfaction_surveys", "complaints"]
    extra = [
        (table, "2023-06-18", [{**data[table][0], "process_date": "2023-06-18"}])
        for table in tables
    ]
    manifest, raw = raw_release(tmp_path, data, extra)
    _, result = prepare(manifest, raw, tmp_path / "processed")
    for table in tables:
        assert result["tables"][table]["accepted"] == 2
        assert result["tables"][table]["rejected"] == 0
