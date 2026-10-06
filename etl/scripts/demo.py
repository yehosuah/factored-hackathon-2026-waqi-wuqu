"""Operate a separate synthetic demo with a stub or explicit local learned classifier."""

import argparse
import json
import os
import re
import secrets
import subprocess
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
SECRET_NAMES = (
    "postgres_password",
    "etl_password",
    "backend_password",
    "demo_password",
    "other_demo_password",
    "agent_password",
)


class DemoConfigurationError(ValueError):
    """Safe configuration error code, without credential or response contents."""


def initialize(project, backend, port):
    if os.geteuid() == 0:
        raise DemoConfigurationError("run_demo_as_non_root_owner")
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", project) or not 1024 <= port <= 65535:
        raise DemoConfigurationError("invalid_demo_project_or_port")
    backend = Path(backend).resolve()
    if not (backend / "Dockerfile").is_file():
        raise DemoConfigurationError("backend_checkout_with_dockerfile_required")
    if not all(
        (backend / name).is_file()
        for name in ("src/factored_bck/conversation_contract.py", "deploy/handoff-read-grants.sql")
    ):
        raise DemoConfigurationError("reviewed_backend_conversation_and_handoff_checkout_required")
    state = REPOSITORY / ".demo" / project
    for directory in (state.parent, state):
        if directory.is_symlink():
            raise DemoConfigurationError("unsafe_demo_state")
        directory.mkdir(mode=0o700, exist_ok=True)
        if directory.stat().st_uid != os.geteuid():
            raise DemoConfigurationError("demo_state_requires_owner")
        os.chmod(directory, 0o700)
    settings = {
        "source_kind": "team_generated_fixture",
        "project": project,
        "backend": str(backend),
        "port": port,
        "uid": os.geteuid(),
        "gid": os.getegid(),
    }
    marker = state / "runtime.json"
    if marker.is_symlink():
        raise DemoConfigurationError("unsafe_demo_marker")
    first_run = not marker.exists()
    if marker.exists():
        if json.loads(marker.read_text()) != settings:
            raise DemoConfigurationError("existing_demo_configuration_differs_use_new_project")
    else:
        if any(state.iterdir()):
            raise DemoConfigurationError("refuse_nonempty_unmarked_demo_state")
        with marker.open("x") as output:
            json.dump(settings, output, sort_keys=True)
        os.chmod(marker, 0o600)
    for name in ("raw", "extract", "processed", "secrets"):
        directory = state / name
        if directory.is_symlink():
            raise DemoConfigurationError("unsafe_demo_directory")
        directory.mkdir(mode=0o700, exist_ok=True)
        if directory.stat().st_uid != os.geteuid():
            raise DemoConfigurationError("demo_directory_requires_owner")
        os.chmod(directory, 0o700)
    for name in SECRET_NAMES:
        path = state / "secrets" / name
        if path.is_symlink():
            raise DemoConfigurationError("unsafe_demo_secret")
        if not path.exists():
            if not first_run:
                raise DemoConfigurationError("existing_demo_secret_missing")
            with path.open("x") as output:
                output.write(secrets.token_urlsafe(32) + "\n")
        if not path.is_file() or not path.stat().st_size or path.stat().st_uid != os.geteuid():
            raise DemoConfigurationError("invalid_demo_secret")
        if path.stat().st_nlink != 1 or path.stat().st_size > 201:
            raise DemoConfigurationError("unsafe_demo_secret")
        os.chmod(path, 0o600)
    return state, settings


def validate_adapter(settings):
    """Validate a requested build/recreation or classifier verification."""
    adapter = os.getenv("DEMO_CONVERSATION_ADAPTER", "stub")
    if adapter not in ("stub", "classifier"):
        raise DemoConfigurationError("unsupported_demo_conversation_adapter")
    if adapter == "classifier":
        artifact = Path(settings["backend"]) / "src/factored_bck/intent/intent_model_v1.json"
        if artifact.is_symlink() or not artifact.is_file():
            raise DemoConfigurationError("reviewed_trained_classifier_backend_required")


def compose(state, settings, *arguments, capture=False, runner=None):
    if arguments and arguments[0] in ("build", "up"):
        validate_adapter(settings)
    adapter = os.getenv("DEMO_CONVERSATION_ADAPTER", "stub")
    env = {
        **os.environ,
        "COMPOSE_PROJECT_NAME": settings["project"],
        "DEMO_STATE": str(state),
        "DEMO_UID": str(settings["uid"]),
        "DEMO_GID": str(settings["gid"]),
        "DEMO_PORT": str(settings["port"]),
        "BCK_BUILD_CONTEXT": settings["backend"],
        "DEMO_CONVERSATION_ADAPTER": adapter,
    }
    endpoint = env.get("DOCKER_HOST") if not env.get("DOCKER_CONTEXT") else None
    if not endpoint:
        context = subprocess.run(
            ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
            env=env,
            text=True,
            check=True,
            capture_output=True,
        )
        endpoint = context.stdout.strip()
    if not endpoint.startswith("unix://"):
        raise DemoConfigurationError("demo_requires_local_unix_docker_endpoint")
    projects = subprocess.run(
        [
            "docker",
            "ps",
            "--all",
            "--filter",
            "label=com.docker.compose.project=" + settings["project"],
            "--format",
            '{{.Label "com.docker.compose.project.working_dir"}}',
        ],
        env=env,
        text=True,
        check=True,
        capture_output=True,
    )
    if any(line != str(REPOSITORY) for line in projects.stdout.splitlines()):
        raise DemoConfigurationError("demo_project_belongs_to_another_checkout")
    verify_demo_volume(state, settings, env)
    # No inherited .env or COMPOSE_FILE can redirect this isolated runtime.
    env.pop("COMPOSE_FILE", None)
    return (runner or subprocess.run)(
        [
            "docker",
            "compose",
            "--env-file",
            os.devnull,
            "-p",
            settings["project"],
            "-f",
            str(REPOSITORY / "compose.demo.yaml"),
            *arguments,
        ],
        cwd=REPOSITORY,
        env=env,
        text=True,
        check=True,
        capture_output=capture,
    )


def verify_demo_volume(state, settings, env):
    """A retained database must belong to this checkout, even with no containers."""
    volume_name = settings["project"] + "_demo-postgres"
    volumes = subprocess.run(
        ["docker", "volume", "ls", "--format", "{{.Name}}"],
        env=env,
        text=True,
        check=True,
        capture_output=True,
    )
    if volume_name not in volumes.stdout.splitlines():
        return
    metadata = json.loads(
        subprocess.run(
            ["docker", "volume", "inspect", volume_name, "--format", "{{json .}}"],
            env=env,
            text=True,
            check=True,
            capture_output=True,
        ).stdout
    )
    # Adopt only with a matching existing PostgreSQL container, then retain its
    # immutable volume identity for down/up. Do not change volume configuration:
    # Compose can otherwise prompt to recreate a database whose labels changed.
    identity = {key: metadata[key] for key in ("Name", "CreatedAt", "Driver")}
    identity.update(checkout=str(REPOSITORY), state=str(state))
    marker = state / "volume-owner.json"
    if marker.is_symlink():
        raise DemoConfigurationError("unsafe_demo_volume_marker")
    if marker.exists():
        if (
            not marker.is_file()
            or marker.stat().st_uid != os.geteuid()
            or marker.stat().st_nlink != 1
            or marker.stat().st_size > 2048
        ):
            raise DemoConfigurationError("unsafe_demo_volume_marker")
        if json.loads(marker.read_text()) != identity:
            raise DemoConfigurationError("demo_volume_identity_changed")
        return
    containers = subprocess.run(
        [
            "docker",
            "ps",
            "--all",
            "--filter",
            "label=com.docker.compose.project=" + settings["project"],
            "--filter",
            "label=com.docker.compose.service=postgres",
            "--format",
            "{{.ID}}",
        ],
        env=env,
        text=True,
        check=True,
        capture_output=True,
    ).stdout.splitlines()
    for container in containers:
        mounts = json.loads(
            subprocess.run(
                ["docker", "inspect", container, "--format", "{{json .Mounts}}"],
                env=env,
                text=True,
                check=True,
                capture_output=True,
            ).stdout
        )
        database = any(
            m.get("Name") == volume_name and m.get("Destination") == "/var/lib/postgresql/data"
            for m in mounts
        )
        secret = str(state / "secrets/postgres_password")
        own_secret = any(
            m.get("Destination") == "/run/secrets/postgres_password"
            and m.get("Source") in (secret, "/host_mnt" + secret)
            for m in mounts
        )
        if database and own_secret:
            with marker.open("x") as output:
                json.dump(identity, output, sort_keys=True)
            os.chmod(marker, 0o600)
            return
    raise DemoConfigurationError("unowned_preserved_demo_volume_use_new_project")


def running_adapter(state, settings):
    """Read only the adapter selection from the running backend, never shell intent."""
    backend = compose(
        state, settings, "ps", "--status", "running", "--quiet", "backend", capture=True
    )
    if not backend.stdout.strip():
        return None
    selection = compose(
        state,
        settings,
        "exec",
        "-T",
        "backend",
        "python",
        "-c",
        "import os; print(os.environ.get('BCK_CONVERSATION_ADAPTER', 'stub'))",
        capture=True,
    ).stdout.strip()
    if selection not in ("stub", "classifier"):
        raise DemoConfigurationError("unsupported_running_demo_conversation_adapter")
    return selection


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("init", "up", "down", "status", "logs", "restart", "rebuild-backend", "verify"),
    )
    parser.add_argument("--backend-path", type=Path, default=REPOSITORY / "FactoredAI_BCK")
    parser.add_argument("--project", default="factored-demo")
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        state, settings = initialize(args.project, args.backend_path, args.port)
        if args.action == "up":
            compose(state, settings, "build")
            compose(state, settings, "up", "-d", "--wait", "--wait-timeout", "180")
        elif args.action == "rebuild-backend":
            compose(state, settings, "build", "backend")
            compose(
                state,
                settings,
                "up",
                "--no-deps",
                "-d",
                "--wait",
                "--wait-timeout",
                "180",
                "backend",
            )
        elif args.action == "down":
            compose(state, settings, "down")  # Preserve database volumes and generated secrets.
        elif args.action == "status":
            compose(state, settings, "ps", "--all")
        elif args.action == "logs":
            compose(state, settings, "logs", "--tail", "30", "etl")
        elif args.action == "restart":
            compose(state, settings, "restart", "postgres", "etl", "backend")
        elif args.action == "verify":
            validate_adapter(settings)
            from verify_demo import verify

            print(json.dumps(verify(state, settings), sort_keys=True))
            return 0
        print(
            json.dumps(
                {
                    "status": "ready" if args.action in ("up", "rebuild-backend") else "completed",
                    "action": args.action,
                    "data_source": settings["source_kind"],
                    "conversation_adapter": running_adapter(state, settings)
                    if args.action != "init"
                    else None,
                    "backend_url": f"http://127.0.0.1:{settings['port']}",
                    "private_state": str(state),
                }
            )
        )
        return 0
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_code": str(error)
                    if isinstance(error, DemoConfigurationError)
                    else type(error).__name__,
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
