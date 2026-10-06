"""The portable demo must publish complete synthetic data, without organizer inputs."""

import json

import pytest

from factored_bank.demo.fixture import generate
from factored_bank.etl.transform import prepare


def test_demo_release_prepares_all_rows_and_repeats_without_change(tmp_path):
    raw, extract = tmp_path / "raw", tmp_path / "extract"
    first = generate(raw, extract)
    repeated = generate(raw, extract)
    assert first["raw_release_id"] == repeated["raw_release_id"]
    assert first["objects"] == 9 and first["rows"] == 13
    _, release = prepare(extract / "demo-manifest.json", raw, tmp_path / "processed")
    assert release["source_kind"] == "team_generated_fixture"
    assert release["ml"]["readiness"] == "not_included"
    assert all(table["input"] == table["accepted"] for table in release["tables"].values())
    assert sum(table["accepted"] for table in release["tables"].values()) == 13
    assert release["tables"]["transactions"]["accepted"] == 3


def test_demo_correction_retains_first_release(tmp_path):
    raw, extract = tmp_path / "raw", tmp_path / "extract"
    first = generate(raw, extract)
    second = generate(raw, extract, revision=2)
    assert first["raw_release_id"] != second["raw_release_id"]
    assert (extract / "releases" / first["raw_release_id"] / "manifest.json").is_file()
    assert (
        json.loads((extract / "demo-manifest.json").read_text())["release_id"]
        == second["raw_release_id"]
    )


def test_demo_refuses_existing_unmarked_state(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    sentinel = raw / "existing-private-input"
    sentinel.write_text("Invented sentinel.")
    with pytest.raises(ValueError, match="refuse_nonempty_unmarked_demo_state"):
        generate(raw, tmp_path / "extract")
    assert sentinel.read_text() == "Invented sentinel."
