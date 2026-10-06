"""Optional ML delivery with invented fixtures; no organizer rows or cloud access."""

import json
import os
from pathlib import Path

import pytest
from etl_fixtures import raw_release

from factored_bank.etl import cli
from factored_bank.etl.common import digest_file
from factored_bank.etl.transform import prepare, verify_release
from factored_bank.profile import profile_release


@pytest.fixture(autouse=True)
def isolated_configuration(monkeypatch):
    monkeypatch.delenv("ETL_ML_ROOT", raising=False)
    mask = os.umask(0o077)
    yield
    os.umask(mask)


@pytest.fixture
def pack(tmp_path):
    root = tmp_path / "ml"
    root.mkdir()
    records = {
        "policies.jsonl": {"document_id": "test-policy"},
        "intent_cases.jsonl": {"example_id": "test-intent", "candidate_intents": ["test-label"]},
        "retrieval_cases.jsonl": {
            "example_id": "test-retrieval",
            "candidate_relevant_document_ids": ["test-policy"],
        },
        "handoff_cases.jsonl": {
            "example_id": "test-handoff",
            "candidate_relevant_policy_ids": ["test-policy"],
        },
    }
    members = []
    for name, record in records.items():
        path = root / name
        path.write_text(json.dumps({**record, "source_kind": "team_synthetic", "language": "es"}))
        members.append(
            {
                "path": name,
                "bytes": path.stat().st_size,
                "sha256": digest_file(path),
                "record_count": 1,
            }
        )
    (root / "contract.json").write_text(json.dumps({"scored_evaluation_authorized": False}))
    (root / "taxonomy.json").write_text(json.dumps({"labels": [{"id": "test-label"}]}))
    (root / "README.md").write_text("Invented test fixture. Not a reviewed ML dataset.\n")
    for name in ("contract.json", "taxonomy.json", "README.md"):
        path = root / name
        members.append({"path": name, "bytes": path.stat().st_size, "sha256": digest_file(path)})
    (root / "manifest.json").write_text(
        json.dumps({"source_kind": "team_synthetic", "files": members})
    )
    return root


def test_no_pack_is_deterministic_across_fresh_outputs_and_profileable(tmp_path):
    manifest, raw = raw_release(tmp_path)
    directory, first = prepare(manifest, raw, tmp_path / "first")
    _, second = prepare(manifest, raw, tmp_path / "second", ml_root=None)
    assert first["release_id"] == second["release_id"]
    assert first["ml"] == {"readiness": "not_included"}
    assert not (directory / "ml").exists()
    assert len(first["files"]) == 18
    assert first == verify_release(directory)
    report = profile_release(directory.name, directory.parent.parent)
    assert report["release_provenance"]["publication_status"] == "not_checked"
    assert all(t["accepted"] == 1 for t in report["reconciliation"].values())


def test_valid_pack_and_changed_pack_have_distinct_identities(tmp_path, pack):
    manifest, raw = raw_release(tmp_path)
    out = tmp_path / "processed"
    _, absent = prepare(manifest, raw, out)
    directory, included = prepare(manifest, raw, out, pack)
    _, repeat = prepare(manifest, raw, out, pack)
    assert included == repeat == verify_release(directory)
    assert included["release_id"] != absent["release_id"]
    assert included["tables"] == absent["tables"]
    assert included["ml"]["readiness"] == "exploration_ready"
    assert included["ml"]["scored_evaluation_authorized"] is False
    assert len(included["files"]) == 26
    (pack / "README.md").write_text("Changed test documentation.\n")
    with pytest.raises(ValueError, match="ml_source_content_mismatch"):
        prepare(manifest, raw, out, pack)
    source_manifest = json.loads((pack / "manifest.json").read_text())
    readme = pack / "README.md"
    for member in source_manifest["files"]:
        if member["path"] == "README.md":
            member.update(bytes=readme.stat().st_size, sha256=digest_file(readme))
    (pack / "manifest.json").write_text(json.dumps(source_manifest))
    changed_dir, changed = prepare(manifest, raw, out, pack)
    assert changed["release_id"] != included["release_id"]
    assert (changed_dir / "ml/README.md").read_text() == "Changed test documentation.\n"
    assert verify_release(directory) == included


@pytest.mark.parametrize("damage", ["missing", "invalid_json", "checksum", "approval", "readme"])
def test_explicit_invalid_pack_never_falls_back_or_reuses_good_cache(tmp_path, pack, damage):
    manifest, raw = raw_release(tmp_path)
    out = tmp_path / "processed"
    directory, good = prepare(manifest, raw, out, pack)
    if damage == "missing":
        pack = tmp_path / "missing"
    elif damage == "invalid_json":
        (pack / "manifest.json").write_text("not json")
    elif damage == "checksum":
        (pack / "policies.jsonl").write_text("changed")
    elif damage == "approval":
        (pack / "contract.json").write_text('{"scored_evaluation_authorized": true}')
    else:
        (pack / "README.md").unlink()
    with pytest.raises((OSError, ValueError)):
        prepare(manifest, raw, out, pack)
    assert verify_release(directory) == good
    assert list((out / "releases").iterdir()) == [directory]
    assert not (out / "current.json").exists()


@pytest.mark.parametrize("action", ["run", "serve", "prepare"])
def test_cli_defaults_to_no_pack(action):
    assert cli.parser().parse_args([action]).ml_root is None


def test_cli_environment_and_explicit_path_precedence(monkeypatch):
    monkeypatch.setenv("ETL_ML_ROOT", "/configured/pack")
    assert cli.parser().parse_args(["run"]).ml_root == Path("/configured/pack")
    assert cli.parser().parse_args(["run", "--ml-root", "/chosen/pack"]).ml_root == Path(
        "/chosen/pack"
    )
    monkeypatch.setenv("ETL_ML_ROOT", "")
    # An explicit valid CLI choice overrides even an invalid environment default.
    assert cli.parser().parse_args(["run", "--ml-root", "/chosen/pack"]).ml_root == Path(
        "/chosen/pack"
    )


@pytest.mark.parametrize("origin", ["environment", "argument"])
def test_empty_explicit_path_is_not_an_implicit_current_directory(monkeypatch, origin):
    args = ["run"]
    if origin == "environment":
        monkeypatch.setenv("ETL_ML_ROOT", "")
    else:
        args += ["--ml-root", ""]
    with pytest.raises(SystemExit) as error:
        cli.parser().parse_args(args)
    assert error.value.code == 2


@pytest.mark.parametrize("configuration", ["absent", "argument", "environment", "missing"])
def test_cli_offline_run_passes_selected_pack_and_never_publishes_invalid_input(
    tmp_path, pack, monkeypatch, capsys, configuration
):
    manifest, raw = raw_release(tmp_path)
    out = tmp_path / "processed"
    published = []

    def publish(directory):
        result = verify_release(directory)
        published.append(result)
        return {"status": "published", "release_id": result["release_id"]}

    def no_extract(*args):
        raise AssertionError("Pinned local manifest must not invoke Extract or S3")

    monkeypatch.setattr(cli, "record_run", lambda run: None)
    monkeypatch.setattr(cli, "publish", publish)
    monkeypatch.setattr(cli, "_extract", no_extract)
    args = [
        "run",
        "--offline",
        "--manifest",
        manifest,
        "--raw-root",
        str(raw),
        "--output-root",
        str(out),
    ]
    if configuration == "argument":
        args += ["--ml-root", str(pack)]
    elif configuration == "environment":
        monkeypatch.setenv("ETL_ML_ROOT", str(pack))
    elif configuration == "missing":
        args += ["--ml-root", str(tmp_path / "missing")]
    assert cli.main(args) == (1 if configuration == "missing" else 0)
    result = json.loads(capsys.readouterr().out)
    if configuration == "missing":
        assert result["status"] == "failed" and not published
    else:
        assert result["status"] == "succeeded" and len(published) == 1
        readiness = "not_included" if configuration == "absent" else "exploration_ready"
        assert published[0]["ml"]["readiness"] == readiness


@pytest.mark.parametrize("name", ["contract.json", "taxonomy.json", "manifest.json", "README.md"])
@pytest.mark.parametrize("destination", ["inside", "outside", "dangling"])
@pytest.mark.parametrize("entrypoint", ["prepare_cached", "copy"])
def test_unsafe_ml_auxiliary_files_are_rejected(tmp_path, pack, name, destination, entrypoint):
    from factored_bank.etl.transform import _copy_ml

    raw_manifest, raw = raw_release(tmp_path)
    out = tmp_path / "processed"
    directory, original = prepare(raw_manifest, raw, out, pack)
    source = pack / name
    # Keep identical bytes so a cached identity cannot conceal an unsafe source path.
    target = (pack if destination == "inside" else tmp_path) / ("target-" + name + ".payload")
    if destination != "dangling":
        target.write_bytes(source.read_bytes())
    source.unlink()
    source.symlink_to(target)
    with pytest.raises(ValueError, match="^unsafe_ml_source_path$"):
        if entrypoint == "prepare_cached":
            prepare(raw_manifest, raw, out, pack)
        else:
            stage = tmp_path / "copy-stage"
            stage.mkdir()
            _copy_ml(pack, stage, {"files": []})
    assert verify_release(directory) == original
    assert list((out / "releases").iterdir()) == [directory]
    assert not (out / "current.json").exists()


@pytest.mark.parametrize("name", ["contract.json", "taxonomy.json", "README.md"])
def test_unlisted_ml_metadata_cannot_be_copied_or_reuse_cached_release(tmp_path, pack, name):
    raw_manifest, raw = raw_release(tmp_path)
    output = tmp_path / "processed"
    directory, good = prepare(raw_manifest, raw, output, pack)
    manifest_path = pack / "manifest.json"
    source = json.loads(manifest_path.read_text())
    source["files"] = [entry for entry in source["files"] if entry["path"] != name]
    manifest_path.write_text(json.dumps(source))
    with pytest.raises(ValueError, match="ml_source_membership_mismatch"):
        prepare(raw_manifest, raw, output, pack)
    assert verify_release(directory) == good
    assert list((output / "releases").iterdir()) == [directory]
    assert not (output / "current.json").exists()


def test_omitted_readme_symlink_cannot_copy_private_sentinel(tmp_path, pack):
    manifest, raw = raw_release(tmp_path)
    source_manifest = json.loads((pack / "manifest.json").read_text())
    source_manifest["files"] = [
        member for member in source_manifest["files"] if member["path"] != "README.md"
    ]
    (pack / "manifest.json").write_text(json.dumps(source_manifest))
    sentinel = tmp_path / "invented-secret.txt"
    sentinel.write_text("Team test sentinel; never an actual credential.")
    (pack / "README.md").unlink()
    (pack / "README.md").symlink_to(sentinel)
    output = tmp_path / "processed"
    with pytest.raises(ValueError, match="unsafe_ml_source_path"):
        prepare(manifest, raw, output, pack)
    assert not (output / "releases").exists()


@pytest.mark.parametrize("name", ["manifest.json", "README.md", "policies.jsonl"])
def test_non_regular_ml_inputs_are_rejected_without_blocking(tmp_path, pack, name):
    import subprocess
    import sys

    manifest, raw = raw_release(tmp_path)
    path = pack / name
    path.unlink()
    os.mkfifo(path, mode=0o600)
    if name != "manifest.json":
        source_manifest = json.loads((pack / "manifest.json").read_text())
        for member in source_manifest["files"]:
            if member["path"] == name:
                member["bytes"] = 0  # A FIFO's size must not let it reach a blocking read.
        (pack / "manifest.json").write_text(json.dumps(source_manifest))
    command = (
        "from pathlib import Path; import sys; "
        "from factored_bank.etl.transform import prepare; "
        "prepare(*[Path(arg) for arg in sys.argv[1:]])"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            command,
            str(manifest),
            str(raw),
            str(tmp_path / "processed"),
            str(pack),
        ],
        capture_output=True,
        text=True,
        timeout=4,
        check=False,
    )
    assert result.returncode != 0
    assert "unsafe_ml_source_path" in result.stderr
    assert not (tmp_path / "processed/releases").exists()


def test_path_swap_during_metadata_copy_cannot_publish_private_sentinel(
    tmp_path, pack, monkeypatch
):
    import shutil

    manifest, raw = raw_release(tmp_path)
    readme = pack / "README.md"
    original = readme.read_bytes()
    saved = pack / "saved-readme.payload"
    sentinel = tmp_path / "private-fixture.txt"
    sentinel.write_text("Invented private sentinel; never an actual credential.")
    swapped = False
    copy_file = shutil.copyfile
    copy_stream = shutil.copyfileobj
    open_path = Path.open
    swaps = 0

    def swap_before_copy(source, destination, *args, **kwargs):
        nonlocal swapped, swaps
        if Path(source) == readme:
            readme.rename(saved)
            readme.symlink_to(sentinel)
            swapped = True
            swaps += 1
        return copy_file(source, destination, *args, **kwargs)

    def restore_before_final_identity(path, *args, **kwargs):
        nonlocal swapped
        if path == pack / "manifest.json" and swapped:
            readme.unlink()
            saved.rename(readme)
            swapped = False
        return open_path(path, *args, **kwargs)

    def swap_after_descriptor_open(source, destination, *args, **kwargs):
        nonlocal swaps
        if os.fstat(source.fileno()).st_ino != readme.stat().st_ino:
            return copy_stream(source, destination, *args, **kwargs)
        readme.rename(saved)
        readme.symlink_to(sentinel)
        swaps += 1
        try:
            return copy_stream(source, destination, *args, **kwargs)
        finally:
            readme.unlink()
            saved.rename(readme)

    monkeypatch.setattr(shutil, "copyfileobj", swap_after_descriptor_open)
    monkeypatch.setattr(shutil, "copyfile", swap_before_copy)
    monkeypatch.setattr(Path, "open", restore_before_final_identity)
    output = tmp_path / "processed"
    try:
        directory, _ = prepare(manifest, raw, output, pack)
    except ValueError as error:
        assert str(error) in ("unsafe_ml_source_path", "ml_source_content_mismatch")
        assert not (output / "releases").exists()
    else:
        assert (directory / "ml/README.md").read_bytes() == original
        assert sentinel.read_bytes() != (directory / "ml/README.md").read_bytes()
    assert swaps == 1


@pytest.mark.parametrize("replacement", ["symlink", "fifo"])
def test_swap_at_metadata_open_is_rejected(tmp_path, pack, monkeypatch, replacement):
    manifest, raw = raw_release(tmp_path)
    readme = pack / "README.md"
    sentinel = tmp_path / "private-fixture.txt"
    sentinel.write_text("Invented sentinel, never a real credential.")
    open_file = os.open
    reads = 0

    def swap_at_open(path, flags, *args, **kwargs):
        nonlocal reads
        if path == "README.md" and kwargs.get("dir_fd") is not None:
            reads += 1
            if reads == 2:  # Identity was checked; now opening for the staged copy.
                readme.unlink()
                if replacement == "symlink":
                    readme.symlink_to(sentinel)
                else:
                    os.mkfifo(readme)
        return open_file(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", swap_at_open)
    output = tmp_path / "processed"
    with pytest.raises(ValueError, match="^unsafe_ml_source_path$"):
        prepare(manifest, raw, output, pack)
    assert reads == 2
    assert not (output / "releases").exists()
    assert not list((output / "staging").iterdir())
