"""Private demo setup must preserve credentials and refuse unsafe or partial state."""

import hashlib
import importlib.util
import os
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "demo_bootstrap", Path(__file__).parents[1] / "scripts/demo.py"
)
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.delenv("DEMO_CONVERSATION_ADAPTER", raising=False)
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "Dockerfile").write_text("FROM scratch\n")
    for name in ("src/factored_bck/conversation_contract.py", "deploy/handoff-read-grants.sql"):
        path = backend / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture capability marker\n")
    monkeypatch.setattr(bootstrap, "REPOSITORY", tmp_path)
    return backend


@pytest.mark.parametrize("adapter", ["external", "classifier"])
def test_invalid_or_unavailable_adapter_fails_before_docker(setup, monkeypatch, adapter):
    state, settings = bootstrap.initialize("proof", setup, 18011)
    monkeypatch.setenv("DEMO_CONVERSATION_ADAPTER", adapter)
    calls = []
    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(ValueError, match="unsupported_demo|reviewed_trained_classifier"):
        bootstrap.compose(state, settings, "up", "-d")
    assert calls == []


@pytest.mark.parametrize("selection", ["classifier", "external"])
@pytest.mark.parametrize(
    "arguments",
    [
        ("ps", "--all"),
        ("restart", "postgres", "etl", "backend"),
        ("logs", "--tail", "30", "etl"),
        ("down",),
        ("ps", "--status", "running", "--quiet", "backend"),
        ("exec", "-T", "backend", "python", "-c", "print('stub')"),
    ],
)
def test_management_of_existing_stub_needs_no_requested_classifier_artifact(
    setup, monkeypatch, selection, arguments
):
    from types import SimpleNamespace

    state, settings = bootstrap.initialize("proof", setup, 18011)
    monkeypatch.setenv("DEMO_CONVERSATION_ADAPTER", selection)
    monkeypatch.setenv("DOCKER_HOST", "unix:///tmp/demo-test.sock")
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    calls = []

    def metadata(command, **kwargs):
        calls.append(command)
        if command[1] == "ps":
            return SimpleNamespace(stdout=str(setup.parent) + "\n")
        if command[1:3] == ["volume", "ls"]:
            return SimpleNamespace(stdout="")
        if command[1] == "compose":
            assert tuple(command[-len(arguments) :]) == arguments
            return SimpleNamespace(stdout="stub\n")
        raise AssertionError("unexpected Docker command")

    monkeypatch.setattr(bootstrap.subprocess, "run", metadata)
    assert bootstrap.compose(state, settings, *arguments, capture=True).stdout == "stub\n"
    assert not (setup / "src/factored_bck/intent/intent_model_v1.json").exists()
    assert any(command[1] == "compose" for command in calls)


def test_classifier_verification_fails_without_artifact_before_docker(setup, monkeypatch, capsys):
    import json

    monkeypatch.setenv("DEMO_CONVERSATION_ADAPTER", "classifier")
    calls = []
    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *args, **kwargs: calls.append(args))
    previous_umask = os.umask(0o077)
    try:
        assert bootstrap.main(["verify", "--backend-path", str(setup)]) == 1
    finally:
        os.umask(previous_umask)
    assert (
        json.loads(capsys.readouterr().out)["error_code"]
        == "reviewed_trained_classifier_backend_required"
    )
    assert calls == []


@pytest.mark.parametrize("action", ["status", "restart"])
@pytest.mark.parametrize("active", ["classifier", "stub", None])
def test_report_uses_running_backend_despite_different_shell_selection(
    setup, monkeypatch, capsys, action, active
):
    import json
    from types import SimpleNamespace

    monkeypatch.setenv(
        "DEMO_CONVERSATION_ADAPTER", "stub" if active == "classifier" else "classifier"
    )
    calls = []

    def control(state, settings, *arguments, **kwargs):
        calls.append(arguments)
        if arguments == ("ps", "--status", "running", "--quiet", "backend"):
            return SimpleNamespace(stdout="running-backend\n" if active else "")
        if arguments[0] == "exec":
            assert active is not None and arguments[2] == "backend"
            assert "BCK_CONVERSATION_ADAPTER" in arguments[-1]
            return SimpleNamespace(stdout=active + "\n")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(bootstrap, "compose", control)
    previous_umask = os.umask(0o077)
    try:
        assert (
            bootstrap.main(
                [action, "--backend-path", str(setup), "--project", "proof", "--port", "18011"]
            )
            == 0
        )
    finally:
        os.umask(previous_umask)
    assert json.loads(capsys.readouterr().out)["conversation_adapter"] == active
    assert not any(call[0] in ("up", "build") for call in calls)


def fingerprints(state):
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (state / "secrets").iterdir()
    }


def test_repeated_private_bootstrap_preserves_all_secrets(setup):
    state, settings = bootstrap.initialize("proof", setup, 18011)
    initial = fingerprints(state)
    repeated, repeated_settings = bootstrap.initialize("proof", setup, 18011)
    assert fingerprints(repeated) == initial
    assert settings == repeated_settings
    assert len(initial) == 6
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in (state / "secrets").iterdir())


def test_missing_existing_secret_is_not_silently_rotated(setup):
    state, _ = bootstrap.initialize("proof", setup, 18011)
    (state / "secrets/etl_password").unlink()
    initial = fingerprints(state)
    with pytest.raises(ValueError, match="existing_demo_secret_missing"):
        bootstrap.initialize("proof", setup, 18011)
    assert fingerprints(state) == initial


def test_symlinked_state_cannot_change_external_directory(setup):
    outside = setup.parent / "outside"
    outside.mkdir(mode=0o755)
    (setup.parent / ".demo").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="unsafe_demo_state"):
        bootstrap.initialize("proof", setup, 18011)
    assert not list(outside.iterdir())
    assert outside.stat().st_mode & 0o777 == 0o755


def test_remote_daemon_is_rejected_before_any_compose_action(setup, monkeypatch):
    state, settings = bootstrap.initialize("proof", setup, 18011)
    monkeypatch.setenv("DOCKER_HOST", "ssh://deployment.example.test")
    calls = []
    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(ValueError, match="demo_requires_local_unix_docker_endpoint"):
        bootstrap.compose(state, settings, "up", "-d")
    assert calls == []


def test_foreign_project_cannot_be_recreated_or_stopped(setup, monkeypatch):
    from types import SimpleNamespace

    state, settings = bootstrap.initialize("proof", setup, 18011)
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    calls = []

    def docker_metadata(arguments, **kwargs):
        calls.append(arguments)
        if arguments[1] == "context":
            return SimpleNamespace(stdout="unix:///tmp/demo-test.sock\n")
        if arguments[1] == "ps":
            return SimpleNamespace(stdout="/another/checkout\n")
        raise AssertionError("foreign project was mutated")

    monkeypatch.setattr(bootstrap.subprocess, "run", docker_metadata)
    with pytest.raises(ValueError, match="demo_project_belongs_to_another_checkout"):
        bootstrap.compose(state, settings, "down")
    assert len(calls) == 2


def test_old_backend_checkout_cannot_claim_complete_demo_readiness(setup):
    (setup / "src/factored_bck/conversation_contract.py").unlink()
    with pytest.raises(
        ValueError, match="reviewed_backend_conversation_and_handoff_checkout_required"
    ):
        bootstrap.initialize("proof", setup, 18011)
    assert not (setup.parent / ".demo").exists()


@pytest.mark.parametrize("foreign", ["unlabelled", "checkout", "state"])
def test_preserved_foreign_database_is_refused_without_containers(setup, monkeypatch, foreign):
    import json
    from types import SimpleNamespace

    state, settings = bootstrap.initialize("proof", setup, 18011)
    monkeypatch.setenv("DOCKER_HOST", "unix:///tmp/demo-test.sock")
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    labels = {
        "io.factored.demo.checkout": str(setup.parent),
        "io.factored.demo.state": str(state),
    }
    if foreign == "unlabelled":
        labels = {}
    else:
        labels["io.factored.demo." + foreign] = "/another/checkout"
    calls = []

    def metadata(arguments, **kwargs):
        calls.append(arguments)
        if arguments[1] == "ps":
            return SimpleNamespace(stdout="")
        if arguments[1:3] == ["volume", "ls"]:
            return SimpleNamespace(stdout="proof_demo-postgres\n")
        if arguments[1:3] == ["volume", "inspect"]:
            return SimpleNamespace(
                stdout=json.dumps(
                    {
                        "Name": "proof_demo-postgres",
                        "CreatedAt": "fixture-volume-id",
                        "Driver": "local",
                        "Labels": labels,
                    }
                )
            )
        raise AssertionError("Foreign volume reached Compose startup")

    monkeypatch.setattr(bootstrap.subprocess, "run", metadata)
    with pytest.raises(ValueError, match="demo_volume|unowned_preserved"):
        bootstrap.compose(state, settings, "up", "-d")
    assert not any("compose" in call for call in calls)


def test_existing_own_volume_identity_survives_down_but_refuses_replacement(setup, monkeypatch):
    import json
    from types import SimpleNamespace

    state, settings = bootstrap.initialize("proof", setup, 18011)
    existing_container = True
    created = "original-volume"

    def metadata(arguments, **kwargs):
        if arguments[1:3] == ["volume", "ls"]:
            return SimpleNamespace(stdout="proof_demo-postgres\n")
        if arguments[1:3] == ["volume", "inspect"]:
            return SimpleNamespace(
                stdout=json.dumps(
                    {
                        "Name": "proof_demo-postgres",
                        "CreatedAt": created,
                        "Driver": "local",
                        "Labels": {},
                    }
                )
            )
        if arguments[1] == "ps":
            return SimpleNamespace(stdout="owned-postgres\n" if existing_container else "")
        if arguments[1] == "inspect":
            return SimpleNamespace(
                stdout=json.dumps(
                    [
                        {"Name": "proof_demo-postgres", "Destination": "/var/lib/postgresql/data"},
                        {
                            "Source": str(state / "secrets/postgres_password"),
                            "Destination": "/run/secrets/postgres_password",
                        },
                    ]
                )
            )
        raise AssertionError("Unexpected mutation")

    monkeypatch.setattr(bootstrap.subprocess, "run", metadata)
    bootstrap.verify_demo_volume(state, settings, {})
    existing_container = False
    bootstrap.verify_demo_volume(state, settings, {})
    created = "foreign-replacement"
    with pytest.raises(ValueError, match="demo_volume_identity_changed"):
        bootstrap.verify_demo_volume(state, settings, {})
