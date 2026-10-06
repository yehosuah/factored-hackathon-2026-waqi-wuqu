"""Fingerprint executable inputs without serializing local credentials or row data."""

import hashlib
import os
import subprocess
from pathlib import Path


def fingerprint() -> dict:
    package = Path(__file__).resolve().parent.parent
    root = Path(os.getenv("FACTORED_PROVENANCE_ROOT", str(package.parent.parent)))
    h = hashlib.sha256()
    files = sorted(package.rglob("*.py"))
    files += [p for p in (root / "pyproject.toml", root / "uv.lock") if p.is_file()]
    for path in files:
        logical_path = (
            "src/factored_bank/" + str(path.relative_to(package))
            if path.is_relative_to(package)
            else path.name
        )
        h.update(logical_path.encode())
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")

    def git(*args):
        try:
            result = subprocess.run(
                ["git", *args], cwd=root, capture_output=True, text=True, timeout=5, check=False
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            return None

    lock = root / "uv.lock"
    return {
        "code_revision": git("rev-parse", "HEAD"),
        "dirty_worktree": bool(git("status", "--porcelain")),
        "source_tree_digest": h.hexdigest(),
        "dependency_lock_digest": hashlib.sha256(lock.read_bytes()).hexdigest()
        if lock.is_file()
        else None,
    }
