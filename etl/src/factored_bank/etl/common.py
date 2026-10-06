"""Private storage, safe configuration and run coordination."""

import fcntl
import hashlib
import json
import os
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def now():
    return datetime.now(UTC).isoformat()


def digest_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def stable_digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def sync_path(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        with temp.open("x") as f:
            os.chmod(temp, 0o600)
            json.dump(value, f, sort_keys=True, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        temp.unlink(missing_ok=True)


@contextmanager
def run_lock(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".etl.lock").open("a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("run_already_active") from None
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def database_kwargs(prefix="ETL"):
    password_file = os.environ.get(f"{prefix}_DB_PASSWORD_FILE")
    return {
        "host": os.environ.get(f"{prefix}_DB_HOST", "localhost"),
        "port": int(os.environ.get(f"{prefix}_DB_PORT", "5432")),
        "dbname": os.environ.get(f"{prefix}_DB_NAME", "factored"),
        "user": os.environ.get(f"{prefix}_DB_USER", "etl_loader"),
        "password": Path(password_file).read_text().strip() if password_file else "",
        "connect_timeout": 10,
        "application_name": "factored_etl",
    }
