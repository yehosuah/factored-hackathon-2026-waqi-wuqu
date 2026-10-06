"""Behavioral ETL acceptance with team-generated data and no cloud credentials."""

import json

import duckdb
import pytest
from etl_fixtures import raw_release, rows

from factored_bank.etl.common import run_lock
from factored_bank.etl.transform import prepare, verify_release


def test_complete_release_repeat_optional_nulls_and_lineage(tmp_path):
    manifest, raw = raw_release(tmp_path)
    directory, first = prepare(manifest, raw, tmp_path / "processed")
    _, second = prepare(manifest, raw, tmp_path / "processed")
    assert first == second == verify_release(directory)
    assert first["source_kind"] == "team_generated_fixture"
    assert all(
        t["input"] == t["accepted"] == 1 and t["rejected"] == 0 for t in first["tables"].values()
    )
    c = duckdb.connect()
    row = c.execute(
        "SELECT current_balance,credit_limit,_source_sha256,_source_row FROM read_parquet(?)",
        [str(directory / "products.parquet")],
    ).fetchone()
    assert str(row[0]) == "125.50" and row[1] is None and len(row[2]) == 64 and row[3] == 1
    assert not (tmp_path / "processed/current.json").exists()  # Preparation is not publication.


def test_advisory_branch_orphan_does_not_remove_customer(tmp_path):
    data = rows()
    data["customers"][0]["registration_branch_id"] = "missing-team-branch"
    manifest, raw = raw_release(tmp_path, data)
    _, result = prepare(manifest, raw, tmp_path / "processed")
    assert result["tables"]["customers"]["accepted"] == 1
    assert result["tables"]["customers"]["quality_flags"] == {
        "unresolved_reference:registration_branch_id": 1
    }
    assert result["tables"]["transactions"]["accepted"] == 1


def test_money_not_rounded_and_all_rows_reconcile(tmp_path):
    data = rows()
    data["transactions"][0]["amount"] = "12.345"
    manifest, raw = raw_release(tmp_path, data)
    directory, result = prepare(manifest, raw, tmp_path / "processed")
    tx = result["tables"]["transactions"]
    assert (tx["input"], tx["accepted"], tx["rejected"]) == (1, 0, 1)
    assert tx["reasons"]["decimal_scale:amount"] == 1
    rejected = (
        duckdb.connect()
        .execute(
            "SELECT amount,_errors FROM read_parquet(?)",
            [str(directory / "transactions.rejects.parquet")],
        )
        .fetchone()
    )
    assert rejected[0] == "12.345"


def test_conflicting_keys_and_parent_rejection_propagate(tmp_path):
    data = rows()
    data["products"].append({**data["products"][0], "product_id": "products-2"})
    manifest, raw = raw_release(tmp_path, data)
    _, result = prepare(manifest, raw, tmp_path / "processed")
    assert result["tables"]["products"]["accepted"] == 0
    assert result["tables"]["products"]["rejected"] == 2
    assert result["tables"]["transactions"]["rejected"] == 1
    assert result["tables"]["complaints"]["rejected"] == 1


def test_effective_key_preserves_history_across_partitions(tmp_path):
    data = rows()
    late = {**data["transactions"][0], "process_date": "2023-06-18", "amount": "20.00"}
    manifest, raw = raw_release(tmp_path, data, [("transactions", "2023-06-18", [late])])
    _, result = prepare(manifest, raw, tmp_path / "processed")
    assert result["tables"]["transactions"]["accepted"] == 2
    assert result["tables"]["transactions"]["key"] == ["transaction_id", "process_date"]


def test_corruption_rejects_cached_source_and_curated_release(tmp_path):
    manifest, raw = raw_release(tmp_path)
    directory, _ = prepare(manifest, raw, tmp_path / "processed")
    input_manifest = json.loads(__import__("pathlib").Path(manifest).read_text())
    original = raw / input_manifest["objects"][0]["local_path"]
    original.write_bytes(original.read_bytes() + b"corruption")
    with pytest.raises(ValueError, match="raw_content_mismatch"):
        prepare(manifest, raw, tmp_path / "processed")
    path = directory / "products.parquet"
    path.write_bytes(path.read_bytes() + b"corruption")
    with pytest.raises(ValueError, match="curated_content_mismatch"):
        verify_release(directory)


def test_run_lock_excludes_overlap(tmp_path):
    with run_lock(tmp_path):
        with pytest.raises(RuntimeError, match="run_already_active"), run_lock(tmp_path):
            pass
