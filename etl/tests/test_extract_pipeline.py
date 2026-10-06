"""End-to-end Extract contracts using invented team data, never organizer records."""

import csv
import hashlib
import io
import json
from pathlib import Path

import pytest

from factored_bank.extract import pipeline as pipeline_module
from factored_bank.extract.contracts import (
    CONTRACT_VERSION,
    DAILY_TABLES,
    HEADERS,
    ROOT_TABLES,
    VALIDATION_VERSION,
)
from factored_bank.extract.errors import ExtractError
from factored_bank.extract.pipeline import ExtractPipeline
from factored_bank.extract.storage import RawStore


def csv_bytes(table, marker="team-fixture"):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(HEADERS[table])
    writer.writerow([marker] + [""] * (len(HEADERS[table]) - 1))
    return stream.getvalue().encode("utf-8")


def daily_key(table="transactions", day="2023-06-17"):
    year, month, date = day.split("-")
    return f"data/{table}/year={year}/month={month}/day={date}/{table}_{year}{month}{date}.csv"


class FixtureSource:
    """Controlled remote seam with source identities and complete-byte downloads."""

    descriptor = {
        "kind": "team-fixture",
        "bucket": "controlled-extract-test-source",
        "prefix": "data/",
        "region": "us-east-2",
    }

    def __init__(self):
        self.files = {f"data/{table}.csv": csv_bytes(table) for table in ROOT_TABLES}
        self.files.update({daily_key(table): csv_bytes(table) for table in DAILY_TABLES})
        self.list_calls = 0
        self.downloads = []
        self.after_download = None
        self.fail_downloads = False
        self.truncate_key = None

    def identity(self, key):
        payload = self.files[key]
        return {
            "key": key,
            "size": len(payload),
            "etag": '"' + hashlib.sha256(payload).hexdigest() + '"',
            "last_modified": "2026-09-27T00:00:00+00:00",
        }

    def list_objects(self):
        self.list_calls += 1
        return [self.identity(key) for key in sorted(self.files)]

    def download(self, obj, destination):
        if self.fail_downloads:
            raise ExtractError("source_unavailable", "Controlled source unavailable")
        if obj["key"] not in self.files or any(
            obj.get(name) != value for name, value in self.identity(obj["key"]).items()
        ):
            raise ExtractError("source_changed", "Planned identity changed", exit_code=3)
        self.downloads.append(obj["key"])
        payload = self.files[obj["key"]]
        if self.truncate_key == obj["key"]:
            payload = payload[:-4]
        Path(destination).write_bytes(payload)
        if self.after_download:
            callback, self.after_download = self.after_download, None
            callback()
        return {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size": len(payload),
            "version_id": None,
            "remote_checksum": {"status": "unavailable"},
            "attempts": 1,
        }


@pytest.fixture
def setup(tmp_path):
    source = FixtureSource()
    raw = tmp_path / "raw"
    output = tmp_path / "outputs"
    pipeline = ExtractPipeline(source, raw, output, workers=1)
    return source, pipeline, raw, output


def manifest(result):
    return json.loads(Path(result["manifest_path"]).read_text())


def current_bytes(raw, result):
    return (raw / "current" / f"{result['scope_id']}.json").read_bytes()


def assert_accounted(result, expected):
    assert (
        sum(result[field] for field in ("downloaded", "reused", "failed", "not_attempted"))
        == expected
    )


def test_plan_downloads_nothing_and_has_no_publication(setup):
    source, pipeline, raw, _ = setup
    result = pipeline.plan()
    assert result["status"] == "planned"
    assert result["exit_code"] == 0
    assert Path(result["plan_path"]).is_file()
    assert source.downloads == []
    assert not list((raw / "current").glob("*.json"))


def test_initial_repeat_and_offline_verification_preserve_release(setup):
    source, pipeline, raw, _ = setup
    first = pipeline.run()
    assert first["status"] == "published"
    assert first["downloaded"] == 9
    assert sum(entry["attempts"] for entry in first["objects"]) == 9
    assert sum(entry["transferred_bytes"] for entry in first["objects"]) == first["expected_bytes"]
    assert_accounted(first, 9)
    accepted = manifest(first)
    assert {entry["table"] for entry in accepted["objects"]} == set(HEADERS)
    assert sum(entry["validation"]["row_count"] for entry in accepted["objects"]) == 9
    for entry in accepted["objects"]:
        assert (raw / entry["local_path"]).read_bytes() == source.files[entry["source"]["key"]]
    original_files = set((raw / "objects").rglob("*.csv"))
    second = pipeline.run()
    assert second["status"] == "unchanged"
    assert second["run_id"] != first["run_id"]
    assert second["accepted_release_id"] == first["accepted_release_id"]
    assert second["downloaded"] == 0
    assert second["reused"] == 9
    assert sum(entry["attempts"] for entry in second["objects"]) == 0
    assert sum(entry["transferred_bytes"] for entry in second["objects"]) == 0
    assert len(source.downloads) == 9
    assert set((raw / "objects").rglob("*.csv")) == original_files
    calls = source.list_calls
    source.fail_downloads = True
    verified = pipeline.verify(release_id=first["accepted_release_id"])
    assert verified["exit_code"] == 0
    assert source.list_calls == calls


def test_late_partition_and_correction_retain_prior_release(setup):
    source, pipeline, raw, _ = setup
    first = pipeline.run()
    first_manifest = Path(first["manifest_path"]).read_bytes()
    source.files[daily_key(day="2023-06-16")] = csv_bytes("transactions", "late-team-fixture")
    late = pipeline.run()
    assert late["status"] == "published"
    assert (late["downloaded"], late["reused"]) == (1, 9)
    assert len(manifest(late)["objects"]) == 10
    original = source.files["data/products.csv"]
    source.files["data/products.csv"] = csv_bytes("products", "corrected-team-fixture")
    corrected = pipeline.run()
    assert corrected["status"] == "published"
    assert corrected["accepted_release_id"] != late["accepted_release_id"]
    assert (corrected["downloaded"], corrected["reused"]) == (1, 9)
    assert Path(first["manifest_path"]).read_bytes() == first_manifest
    assert any(path.read_bytes() == original for path in (raw / "objects").rglob("*.csv"))
    assert pipeline.verify(release_id=first["accepted_release_id"])["exit_code"] == 0


def test_source_disappearance_requires_review_and_retains_current(setup):
    source, pipeline, raw, _ = setup
    extra = daily_key(day="2023-06-18")
    source.files[extra] = csv_bytes("transactions", "extra-team-fixture")
    first = pipeline.run()
    pointer = current_bytes(raw, first)
    del source.files[extra]
    result = pipeline.run()
    assert result["status"] == "review_required"
    assert result["exit_code"] == 3
    assert current_bytes(raw, first) == pointer
    assert pipeline.verify(release_id=first["accepted_release_id"])["exit_code"] == 0


def test_schema_drift_preserves_raw_evidence_and_previous_pointer(setup):
    source, pipeline, raw, output = setup
    first = pipeline.run()
    pointer = current_bytes(raw, first)
    changed = csv_bytes("products").replace(b"product_id,", b"renamed_product_id,", 1)
    source.files["data/products.csv"] = changed
    result = pipeline.run()
    assert result["status"] == "review_required"
    assert result["exit_code"] == 3
    assert current_bytes(raw, first) == pointer
    assert any(path.is_file() and path.read_bytes() == changed for path in raw.rglob("*"))
    assert_accounted(result, 9)
    # Failed headers and row payloads belong in preserved raw bytes, not diagnostic JSON.
    for report in output.rglob("*.json"):
        assert "renamed_product_id" not in report.read_text()
        assert "team-fixture," not in report.read_text()


def test_final_inventory_drift_holds_candidate_then_reuses_downloads(setup):
    source, pipeline, raw, _ = setup
    extra = daily_key(day="2023-06-18")
    source.after_download = lambda: source.files.update({extra: csv_bytes("transactions", "new")})
    result = pipeline.run()
    assert result["exit_code"] == 3
    assert not list((raw / "current").glob("*.json"))
    retry = pipeline.run()
    assert retry["status"] == "published"
    assert len(manifest(retry)["objects"]) == 10
    assert retry["reused"] > 0


def test_truncated_transfer_never_publishes_success(setup):
    source, pipeline, raw, _ = setup
    source.truncate_key = "data/products.csv"
    result = pipeline.run()
    assert result["exit_code"] != 0
    assert result["status"] in {"failed", "unavailable"}
    assert not list((raw / "current").glob("*.json"))
    assert_accounted(result, 9)


@pytest.mark.parametrize("source_available", [True, False])
def test_corrupt_local_content_is_detected_and_repaired_or_unavailable(setup, source_available):
    source, pipeline, raw, _ = setup
    first = pipeline.run()
    entry = manifest(first)["objects"][0]
    path = raw / entry["local_path"]
    path.write_bytes(b"corrupt-team-fixture\n")
    calls = source.list_calls
    assert pipeline.verify(release_id=first["accepted_release_id"])["exit_code"] != 0
    assert source.list_calls == calls
    source.fail_downloads = not source_available
    result = pipeline.run()
    if source_available:
        assert result["exit_code"] == 0
        assert result["downloaded"] == 1
        assert path.read_bytes() == source.files[entry["source"]["key"]]
        assert pipeline.verify(release_id=first["accepted_release_id"])["exit_code"] == 0
    else:
        assert result["status"] == "unavailable"
        assert result["exit_code"] != 0


def test_pilot_cannot_be_consumed_as_full_history(setup):
    source, pipeline, raw, _ = setup
    source.files[daily_key(day="2023-06-18")] = csv_bytes("transactions", "next-day")
    pilot = pipeline.run(scope="pilot", pilot_date="2023-06-17")
    assert pilot["status"] == "published"
    assert len(manifest(pilot)["objects"]) == 9
    assert pipeline.verify(scope="full")["exit_code"] != 0
    full = pipeline.run()
    assert full["status"] == "published"
    assert full["scope_id"] != pilot["scope_id"]
    assert len(manifest(full)["objects"]) == 10
    assert (full["downloaded"], full["reused"]) == (1, 9)
    assert current_bytes(raw, pilot)


def test_supplied_plan_cannot_hide_new_source_objects(setup):
    source, pipeline, raw, _ = setup
    planned = pipeline.plan()
    source.files[daily_key(day="2023-06-18")] = csv_bytes("transactions", "after-plan")
    result = pipeline.run(plan_path=Path(planned["plan_path"]))
    assert result["exit_code"] == 3
    assert not list((raw / "current").glob("*.json"))
    assert source.downloads == []


def test_coverage_gaps_and_header_only_csv_do_not_invent_records(setup):
    source, pipeline, _, _ = setup
    source.files[daily_key(day="2023-06-19")] = csv_bytes("transactions", "after-gap")
    source.files["data/branches.csv"] = (",".join(HEADERS["branches"]) + "\n").encode()
    result = pipeline.run()
    assert result["status"] == "published"
    release = manifest(result)
    assert len(release["objects"]) == 10
    branch = next(entry for entry in release["objects"] if entry["table"] == "branches")
    assert branch["validation"]["row_count"] == 0
    assert release["coverage"]["transactions"]["missing_date_ranges"] == [
        {"from": "2023-06-18", "through": "2023-06-18", "days": 1}
    ]
    assert not any(
        entry["source"]["key"] == daily_key(day="2023-06-18") for entry in release["objects"]
    )


@pytest.mark.parametrize("problem", ["missing_table", "unexpected_layout"])
def test_incomplete_or_unreviewed_scope_cannot_publish(setup, problem):
    source, pipeline, raw, _ = setup
    if problem == "missing_table":
        del source.files["data/service_agents.csv"]
    else:
        source.files["data/transactions/unexpected.csv"] = csv_bytes("transactions")
    result = pipeline.run()
    assert result["exit_code"] == 3
    assert not list((raw / "current").glob("*.json"))
    assert source.downloads == []


@pytest.mark.parametrize("damage", ["missing", "malformed", "wrong_scope"])
def test_offline_verification_rejects_missing_or_malformed_release_metadata(setup, damage):
    source, pipeline, _, _ = setup
    first = pipeline.run()
    path = Path(first["manifest_path"])
    if damage == "missing":
        path.unlink()
    elif damage == "malformed":
        path.write_text("{not valid JSON")
    else:
        release = json.loads(path.read_text())
        release["scope_id"] = "pilot-forged-scope"
        path.write_text(json.dumps(release))
    calls = source.list_calls
    result = pipeline.verify(release_id=first["accepted_release_id"])
    assert result["status"] == "unavailable"
    assert result["exit_code"] != 0
    assert source.list_calls == calls


def test_named_release_verification_rejects_forged_partition_metadata(setup):
    source, pipeline, _, _ = setup
    first = pipeline.run()
    source.files["data/products.csv"] = csv_bytes("products", "make-first-release-historical")
    assert pipeline.run()["status"] == "published"
    path = Path(first["manifest_path"])
    release = json.loads(path.read_text())
    entry = next(entry for entry in release["objects"] if entry["table"] == "transactions")
    entry["partition_date"] = "2099-01-01"
    path.write_text(json.dumps(release))
    calls = source.list_calls
    result = pipeline.verify(release_id=first["accepted_release_id"])
    assert result["status"] == "unavailable"
    assert result["exit_code"] != 0
    assert source.list_calls == calls


def test_missing_acquisition_index_reuses_previous_release_without_redownload(setup):
    source, pipeline, raw, _ = setup
    first = pipeline.run()
    original_ingestion = {
        entry["source"]["key"]: entry["ingested_at"] for entry in manifest(first)["objects"]
    }
    for index in (raw / "acquisition_index").glob("*.json"):
        index.unlink()
    source.fail_downloads = True
    second = pipeline.run()
    assert second["status"] == "unchanged"
    assert second["accepted_release_id"] == first["accepted_release_id"]
    assert (second["downloaded"], second["reused"]) == (0, 9)
    assert len(source.downloads) == 9
    # A subsequent changed release must preserve ingestion history even when it
    # cannot simply return the original immutable manifest.
    source.fail_downloads = False
    source.files[daily_key(day="2023-06-18")] = csv_bytes("transactions", "late-after-index-loss")
    third = pipeline.run()
    assert third["status"] == "published"
    for entry in manifest(third)["objects"]:
        key = entry["source"]["key"]
        if key in original_ingestion:
            assert entry["ingested_at"] == original_ingestion[key]


@pytest.mark.parametrize("action", ["plan", "run", "verify"])
def test_result_persistence_remains_inside_the_operating_system_lock(setup, monkeypatch, action):
    _, pipeline, raw, output = setup
    if action == "verify":
        assert pipeline.run()["status"] == "published"
    competitor = RawStore(raw, output)
    write = pipeline.store.write_run
    observed = []

    def write_while_locked(run_id, name, data):
        if name == "result.json":
            with pytest.raises(ExtractError) as failure, competitor.lock():
                pytest.fail("Another publisher could enter before the run report was persisted")
            assert failure.value.code == "run_locked"
            observed.append(run_id)
        return write(run_id, name, data)

    monkeypatch.setattr(pipeline.store, "write_run", write_while_locked)
    result = getattr(pipeline, action)()
    assert result["exit_code"] == 0
    assert observed == [result["run_id"]]


def test_named_historical_release_verifies_without_repairing_corrupt_current_pointer(setup):
    source, pipeline, raw, _ = setup
    first = pipeline.run()
    source.files["data/products.csv"] = csv_bytes("products", "new-current-release")
    second = pipeline.run()
    assert second["status"] == "published"
    assert first["accepted_release_id"] != second["accepted_release_id"]
    pointer_path = raw / "current" / f"{second['scope_id']}.json"
    corrupt_pointer = b"{broken current pointer: team fixture}"
    pointer_path.write_bytes(corrupt_pointer)
    calls = source.list_calls
    source.fail_downloads = True
    result = pipeline.verify(release_id=first["accepted_release_id"])
    assert result["status"] == "verified"
    assert result["exit_code"] == 0
    assert result["accepted_release_id"] == first["accepted_release_id"]
    assert source.list_calls == calls
    assert pointer_path.read_bytes() == corrupt_pointer


def test_identical_data_preserves_release_but_records_each_runs_checking_code(setup, monkeypatch):
    _, pipeline, _, _ = setup
    producing_code = {
        "code_revision": "team-fixture-producer",
        "dirty_worktree": False,
        "source_tree_digest": "1" * 64,
        "dependency_lock_digest": "a" * 64,
    }
    checking_code = {
        **producing_code,
        "code_revision": "team-fixture-checker",
        "source_tree_digest": "2" * 64,
    }
    monkeypatch.setattr(pipeline_module, "fingerprint", lambda: dict(producing_code))
    first = pipeline.run()
    assert first["status"] == "published"
    monkeypatch.setattr(pipeline_module, "fingerprint", lambda: dict(checking_code))
    repeat = pipeline.run()
    assert repeat["status"] == "unchanged"
    assert repeat["accepted_release_id"] == first["accepted_release_id"]
    assert first["run_id"] != repeat["run_id"]
    assert manifest(repeat)["provenance"] == producing_code
    for result, expected_provenance in ((first, producing_code), (repeat, checking_code)):
        assert result["provenance"] == expected_provenance
        assert result["contract_version"] == CONTRACT_VERSION
        assert result["validation_version"] == VALIDATION_VERSION
        persisted = json.loads(Path(result["result_path"]).read_text())
        assert persisted["provenance"] == expected_provenance
        assert persisted["contract_version"] == CONTRACT_VERSION
        assert persisted["validation_version"] == VALIDATION_VERSION
