"""Storage fixtures are team-created bytes, never organizer records."""

import hashlib
import json
import os
import stat
from pathlib import Path

import pytest

from factored_bank.extract.errors import ExtractError
from factored_bank.extract.storage import RawStore


@pytest.fixture
def store(tmp_path):
    return RawStore(tmp_path / "raw", tmp_path / "output")


def manifest(release_id="release-1", scope_id="full", run_id="run-1"):
    return {
        "release_id": release_id,
        "scope_id": scope_id,
        "run_id": run_id,
        "status": "accepted",
        "objects": [],
    }


def staged(store, content=b"team_fixture\n1\n"):
    digest = hashlib.sha256(content).hexdigest()
    path = store.staging_path("run-1", digest)
    path.write_bytes(content)
    return path, digest


def test_immutable_content_reuse_and_verified_repair(store):
    path, digest = staged(store)
    relative = store.install(path, digest)
    target = store.raw_root / relative
    original_inode = target.stat().st_ino
    repeat, _ = staged(store)
    assert store.install(repeat, digest) == relative
    assert target.stat().st_ino == original_inode
    target.write_bytes(b"corruption")
    replacement, _ = staged(store)
    store.install(replacement, digest)
    assert target.read_bytes() == b"team_fixture\n1\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_wrong_replacement_preserves_corrupt_evidence(store):
    path, digest = staged(store)
    store.install(path, digest)
    target = store.object_path(digest)
    target.write_bytes(b"damaged")
    replacement, _ = staged(store, b"wrong bytes")
    with pytest.raises(ExtractError, match="checksum"):
        store.install(replacement, digest)
    assert target.read_bytes() == b"damaged"
    assert replacement.exists()


def test_same_release_does_not_rewrite_manifest_and_scopes_stay_separate(store):
    store.publish(manifest(), "full")
    path = store.output_root / "releases/release-1/manifest.json"
    before = path.read_bytes()
    store.publish(manifest(run_id="new-observer"), "full")
    assert path.read_bytes() == before
    assert store.read_current("full")["run_id"] == "run-1"
    store.publish(manifest("pilot-release", "pilot", "pilot-run"), "pilot")
    assert store.read_current("full")["release_id"] == "release-1"
    assert store.read_current("pilot")["release_id"] == "pilot-release"


@pytest.mark.parametrize("point", ["before", "after"])
def test_crash_at_pointer_commit_has_unambiguous_publication(store, monkeypatch, point):
    store.publish(manifest(), "full")
    store.write_run(
        "run-1", "result.json", {"status": "published", "accepted_release_id": "release-1"}
    )
    replace = os.replace

    def crash(source, target):
        if Path(target) == store.raw_root / "current/full.json":
            if point == "after":
                replace(source, target)
            raise OSError("simulated power loss")
        replace(source, target)

    monkeypatch.setattr(os, "replace", crash)
    with pytest.raises(OSError):
        store.publish(manifest("release-2", run_id="run-2"), "full")
    monkeypatch.setattr(os, "replace", replace)
    restarted = RawStore(store.raw_root, store.output_root)
    current = restarted.read_current("full")
    reports = restarted.recover()
    if point == "before":
        assert current["release_id"] == "release-1"
        assert reports == []
    else:
        assert current["release_id"] == "release-2"
        assert reports[0]["status"] == "published"
        assert reports[0]["recovered_from_current_pointer"] is True
        assert (store.output_root / "runs/run-2/recovery.json").exists()
    # The complete but orphaned manifest is retained even before pointer commit.
    assert restarted.load_release("release-2")["status"] == "accepted"


def test_competing_lock_refused_and_released_on_error(store):
    competitor = RawStore(store.raw_root, store.output_root)
    with pytest.raises(RuntimeError), store.lock():
        with pytest.raises(ExtractError) as failure, competitor.lock():
            pytest.fail("Competing invocation acquired the lock")
        assert failure.value.code == "run_locked"
        assert failure.value.exit_code == 5
        raise RuntimeError("run interrupted")
    with competitor.lock():
        pass


@pytest.mark.parametrize("location", ["objects", "staging", "current", ".extract.lock"])
def test_symlinks_in_managed_paths_are_rejected(store, tmp_path, location):
    outside = tmp_path / "outside"
    outside.mkdir()
    (store.raw_root / location).symlink_to(outside)
    with pytest.raises(ExtractError) as failure:
        if location == "objects":
            store.object_path("a" * 64)
        elif location == "staging":
            store.staging_path("run", "a" * 64)
        elif location == "current":
            store.read_current("full")
        else:
            with store.lock():
                pytest.fail("Symlink lock was followed")
    assert failure.value.code == "unsafe_path"
    assert list(outside.iterdir()) == []


def test_symlink_root_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(outside)
    with pytest.raises(ExtractError):
        RawStore(alias / "raw", tmp_path / "output")


@pytest.mark.parametrize("bad_id", ["../escape", "/absolute", "a/b", "", ".", ".."])
def test_path_escape_identifiers_rejected(store, bad_id):
    with pytest.raises(ExtractError):
        store.write_run(bad_id, "result.json", {})
    with pytest.raises(ExtractError):
        store.load_release(bad_id)
    with pytest.raises(ExtractError):
        store.read_current(bad_id)


def test_manifest_tampering_detected_before_current_is_returned(store):
    store.publish(manifest(), "full")
    path = store.output_root / "releases/release-1/manifest.json"
    path.write_text(json.dumps(manifest(run_id="tampered")))
    with pytest.raises(ExtractError) as failure:
        store.read_current("full")
    assert failure.value.code == "manifest_checksum_mismatch"


def test_pointer_manifest_path_escape_rejected(store):
    store.publish(manifest(), "full")
    path = store.raw_root / "current/full.json"
    pointer = json.loads(path.read_text())
    pointer["manifest"] = "../../outside.json"
    path.write_text(json.dumps(pointer))
    with pytest.raises(ExtractError) as failure:
        store.read_current("full")
    assert failure.value.code == "unsafe_path"


def test_wrong_manifest_scope_rejected_even_with_valid_pointer_hash(store):
    store.publish(manifest(), "full")
    path = store.output_root / "releases/release-1/manifest.json"
    path.write_text(json.dumps(manifest(scope_id="pilot")))
    pointer_path = store.raw_root / "current/full.json"
    pointer = json.loads(pointer_path.read_text())
    pointer["manifest_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    pointer_path.write_text(json.dumps(pointer))
    path.with_name("manifest.sha256").write_text(pointer["manifest_sha256"] + "\n")
    with pytest.raises(ExtractError) as failure:
        store.read_current("full")
    assert failure.value.code == "release_invalid"


def test_rejected_release_cannot_publish(store):
    value = {**manifest(), "status": "failed"}
    with pytest.raises(ExtractError):
        store.publish(value, "full")
    assert store.read_current("full") is None


def test_private_cache_and_run_reports_roundtrip(store):
    key = "b" * 64
    assert store.find_cached(key) is None
    assert store.read_current("full") is None
    entry = {"sha256": "a" * 64, "first_acquired_at": "team-fixture-time"}
    store.cache(key, entry)
    assert store.find_cached(key) == entry
    path = store.write_run("run-1", "result.json", {"status": "failed"})
    assert json.loads(path.read_bytes()) == {"status": "failed"}
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_publication_flush_failure_preserves_previous_pointer(store, monkeypatch):
    store.publish(manifest(), "full")

    def fail_fsync(_):
        raise OSError("simulated disk error")

    monkeypatch.setattr(os, "fsync", fail_fsync)
    with pytest.raises(OSError):
        store.publish(manifest("release-2", run_id="run-2"), "full")
    assert store.read_current("full")["release_id"] == "release-1"


def test_acquisition_plan_cannot_be_overwritten(store):
    path = store.write_run("run-1", "plan.json", {"objects": ["fixture-a"]})
    store.write_run("run-1", "plan.json", {"objects": ["fixture-a"]})
    with pytest.raises(ExtractError) as failure:
        store.write_run("run-1", "plan.json", {"objects": ["fixture-b"]})
    assert failure.value.code == "immutable_plan_conflict"
    assert json.loads(path.read_bytes()) == {"objects": ["fixture-a"]}


def test_missing_current_manifest_is_unavailable(store):
    store.publish(manifest(), "full")
    store.manifest_path("release-1").unlink()
    with pytest.raises(ExtractError) as failure:
        store.read_current("full")
    assert failure.value.code == "release_unavailable"


def test_safe_json_read_rejects_outside_file(store, tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    with pytest.raises(ExtractError) as failure:
        store.read_json_safe(outside)
    assert failure.value.code == "unsafe_path"


def test_nonregular_metadata_is_rejected_without_blocking(store):
    parent = store.raw_root / "acquisition_index"
    parent.mkdir()
    os.mkfifo(parent / f"{'a' * 64}.json")
    with pytest.raises(ExtractError) as failure:
        store.find_cached("a" * 64)
    assert failure.value.code == "unsafe_path"


@pytest.mark.parametrize("field,value", [("coverage", {"false_claim": True}), ("run_id", "forged")])
def test_historical_manifest_metadata_tampering_is_detected(store, field, value):
    store.publish(manifest(), "full")
    store.publish(manifest("release-2", run_id="run-2"), "full")
    path = store.manifest_path("release-1")
    modified = json.loads(path.read_bytes())
    modified[field] = value
    path.write_text(json.dumps(modified))
    assert store.read_current("full")["release_id"] == "release-2"
    with pytest.raises(ExtractError) as failure:
        store.load_release("release-1")
    assert failure.value.code == "manifest_checksum_mismatch"


def test_missing_historical_checksum_never_auto_learns_modified_manifest(store):
    store.publish(manifest(), "full")
    path = store.manifest_path("release-1").with_name("manifest.sha256")
    path.unlink()
    with pytest.raises(ExtractError) as failure:
        store.publish(manifest(run_id="new-run"), "full")
    assert failure.value.code == "manifest_checksum_missing"
    assert not path.exists()


@pytest.mark.parametrize("point", ["checksum", "manifest", "directory_commit"])
def test_partial_release_preparation_is_retryable_without_discarding_evidence(
    store, monkeypatch, point
):
    replace = os.replace

    def crash(source, target):
        target = Path(target)
        if (
            (point == "checksum" and target.name == "manifest.sha256")
            or (point == "manifest" and target.name == "manifest.json")
            or (point == "directory_commit" and target.name == "release-1")
        ):
            raise OSError("simulated interruption preparing release")
        replace(source, target)

    monkeypatch.setattr(os, "replace", crash)
    with pytest.raises(OSError):
        store.publish(manifest(), "full")
    monkeypatch.setattr(os, "replace", replace)
    assert not store.manifest_path("release-1").exists()
    assert store.read_current("full") is None
    orphans = list((store.output_root / "releases").glob(".prepared-*"))
    assert len(orphans) == 1
    # Run metadata may change while the deterministic logical release ID stays the same.
    store.publish(manifest(run_id="retry-run"), "full")
    assert store.load_release("release-1")["run_id"] == "retry-run"
    assert store.read_current("full")["run_id"] == "retry-run"
    assert orphans[0].exists()


def test_completed_directory_before_pointer_commit_is_reusable(store, monkeypatch):
    replace = os.replace

    def crash(source, target):
        replace(source, target)
        if Path(target).name == "release-1":
            raise OSError("simulated interruption after release-directory commit")

    monkeypatch.setattr(os, "replace", crash)
    with pytest.raises(OSError):
        store.publish(manifest(), "full")
    monkeypatch.setattr(os, "replace", replace)
    assert store.read_current("full") is None
    assert store.load_release("release-1")["run_id"] == "run-1"
    store.publish(manifest(run_id="retry-run"), "full")
    assert store.read_current("full")["run_id"] == "run-1"
