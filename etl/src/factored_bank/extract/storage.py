"""Private local raw repository and durable publication commit point.

Call mutations inside ``lock()``. A manifest becomes current only when its pointer
is replaced; orphan manifests and staging bytes are deliberately retained.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
import uuid
from contextlib import contextmanager
from pathlib import Path

from .errors import ExtractError

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")


def _identifier(value: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ExtractError("unsafe_path", "Invalid storage identifier", exit_code=2)
    return value


def _digest(value: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ExtractError("unsafe_path", "Invalid content digest", exit_code=2)
    return value


def _check_path(path: Path) -> None:
    """Reject symlinks, including dangling links and existing ancestor links."""
    for component in reversed((path, *path.parents)):
        try:
            metadata = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode):
            raise ExtractError("unsafe_path", "Symlink in managed storage path")
        if component != path and not stat.S_ISDIR(metadata.st_mode):
            raise ExtractError("unsafe_path", "Non-directory storage ancestor")


def _sync_dir(path: Path) -> None:
    _check_path(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _mkdir(path: Path) -> None:
    _check_path(path)
    if path.exists():
        if not path.is_dir():
            raise ExtractError("unsafe_path", "Storage location is not a directory")
        return
    _mkdir(path.parent)
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        _check_path(path)
        if not path.is_dir():
            raise ExtractError("unsafe_path", "Storage location is not a directory") from None
    _sync_dir(path.parent)


def _read_bytes(path: Path) -> bytes:
    _check_path(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ExtractError("unsafe_path", "Storage file is not regular")
        return stream.read()


def _json_bytes(value: dict) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def _decode(data: bytes) -> dict:
    try:
        result = json.loads(data)
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (UnicodeError, ValueError) as exc:
        raise ExtractError("storage_metadata_invalid", "Invalid storage metadata") from exc


def _sha_file(path: Path) -> str:
    _check_path(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ExtractError("unsafe_path", "Storage file is not regular")
        return hashlib.file_digest(stream, "sha256").hexdigest()


class RawStore:
    """Immutable byte storage with separate pilot/full current pointers."""

    def __init__(self, raw_root: Path, output_root: Path):
        self.raw_root = Path(os.path.abspath(raw_root))
        self.output_root = Path(os.path.abspath(output_root))
        try:
            for root in (self.raw_root, self.output_root):
                _mkdir(root)
            if self.raw_root.stat().st_dev != self.output_root.stat().st_dev:
                raise ExtractError(
                    "unsupported_filesystem", "Storage roots must share a local filesystem", 2
                )
            if (
                self.raw_root == self.output_root
                or self.raw_root in self.output_root.parents
                or self.output_root in self.raw_root.parents
            ):
                raise ExtractError("invalid_configuration", "Storage roots must be separate", 2)
        except OSError as exc:
            raise ExtractError("storage_unavailable", "Cannot initialize local storage") from exc

    def _safe(self, path: Path, root: Path) -> Path:
        if not path.is_relative_to(root) or ".." in path.parts:
            raise ExtractError("unsafe_path", "Path escapes managed storage")
        _check_path(path)
        return path

    def _atomic(self, path: Path, payload: bytes) -> None:
        _check_path(path)
        _mkdir(path.parent)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        _check_path(path)
        os.replace(temporary, path)
        _sync_dir(path.parent)

    @contextmanager
    def lock(self):
        """Hold an OS lock; fail immediately when another invocation holds it."""
        path = self._safe(self.raw_root / ".extract.lock", self.raw_root)
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ExtractError("run_locked", "Another Extract run holds the lock", 5) from None
            yield
        finally:
            os.close(descriptor)

    def object_path(self, sha256: str) -> Path:
        digest = _digest(sha256)
        return self._safe(self.raw_root / "objects" / digest[:2] / f"{digest}.csv", self.raw_root)

    def staging_path(self, run_id: str, key_digest: str) -> Path:
        parent = self.raw_root / "staging" / _identifier(run_id)
        _mkdir(parent)
        path = parent / f"{_digest(key_digest)}.{uuid.uuid4().hex}.part"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(descriptor)
        _sync_dir(parent)
        return path

    def install(self, staged: Path, sha256: str) -> str:
        """Finalize verified bytes; a verified replacement can repair damaged content."""
        staged = self._safe(Path(os.path.abspath(staged)), self.raw_root / "staging")
        destination = self.object_path(sha256)
        if _sha_file(staged) != sha256:
            raise ExtractError("local_checksum_mismatch", "Staged content checksum mismatch")
        _mkdir(destination.parent)
        if destination.exists() and _sha_file(destination) == sha256:
            return destination.relative_to(self.raw_root).as_posix()
        descriptor = os.open(staged, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fchmod(descriptor, 0o600)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        _check_path(destination)
        os.replace(staged, destination)
        _sync_dir(destination.parent)
        _sync_dir(staged.parent)
        return destination.relative_to(self.raw_root).as_posix()

    def write_run(self, run_id: str, name: str, data: dict) -> Path:
        path = self.output_root / "runs" / _identifier(run_id) / _identifier(name)
        path = self._safe(path, self.output_root)
        payload = _json_bytes(data)
        if name == "plan.json" and path.exists():
            if _read_bytes(path) != payload:
                raise ExtractError("immutable_plan_conflict", "An acquisition plan cannot change")
            return path
        self._atomic(path, payload)
        return path

    def manifest_path(self, release_id: str) -> Path:
        path = self.output_root / "releases" / _identifier(release_id) / "manifest.json"
        return self._safe(path, self.output_root)

    def read_json_safe(self, path: Path) -> dict:
        path = Path(os.path.abspath(path))
        root = self.raw_root if path.is_relative_to(self.raw_root) else self.output_root
        return _decode(_read_bytes(self._safe(path, root)))

    def load_release(self, release_id: str) -> dict:
        path = self.manifest_path(release_id)
        try:
            content = _read_bytes(self._safe(path, self.output_root))
        except FileNotFoundError as exc:
            raise ExtractError("release_unavailable", "Release manifest is unavailable") from exc
        try:
            checksum = _read_bytes(path.with_name("manifest.sha256"))
        except FileNotFoundError as exc:
            raise ExtractError(
                "manifest_checksum_missing", "Release manifest checksum is unavailable"
            ) from exc
        if not re.fullmatch(rb"[0-9a-f]{64}\n", checksum):
            raise ExtractError("manifest_checksum_invalid", "Invalid manifest checksum record")
        if hashlib.sha256(content).hexdigest().encode() + b"\n" != checksum:
            raise ExtractError("manifest_checksum_mismatch", "Release manifest checksum mismatch")
        manifest = _decode(content)
        if manifest.get("release_id") != release_id or manifest.get("status") != "accepted":
            raise ExtractError("release_invalid", "Invalid accepted release identity or status")
        _identifier(manifest.get("scope_id"))
        return manifest

    def read_current(self, scope_id: str) -> dict | None:
        path = self.raw_root / "current" / f"{_identifier(scope_id)}.json"
        try:
            pointer = _decode(_read_bytes(self._safe(path, self.raw_root)))
        except FileNotFoundError:
            return None
        if pointer.get("scope_id") != scope_id:
            raise ExtractError("release_invalid", "Current pointer has an invalid scope")
        release_id = _identifier(pointer.get("release_id"))
        expected = f"releases/{release_id}/manifest.json"
        if pointer.get("manifest") != expected:
            raise ExtractError("unsafe_path", "Current manifest path is invalid")
        digest = _digest(pointer.get("manifest_sha256"))
        try:
            content = _read_bytes(self._safe(self.output_root / expected, self.output_root))
        except FileNotFoundError as exc:
            raise ExtractError("release_unavailable", "Current manifest is missing") from exc
        if hashlib.sha256(content).hexdigest() != digest:
            raise ExtractError("manifest_checksum_mismatch", "Current manifest checksum mismatch")
        manifest = self.load_release(release_id)
        if manifest["scope_id"] != scope_id:
            raise ExtractError("release_invalid", "Current manifest scope differs")
        if pointer.get("run_id") != manifest.get("run_id"):
            raise ExtractError("release_invalid", "Current manifest producer differs")
        return {**pointer, "manifest_data": manifest}

    def publish(self, manifest: dict, scope_id: str) -> dict:
        scope_id = _identifier(scope_id)
        release_id = _identifier(manifest.get("release_id"))
        if manifest.get("status") != "accepted" or manifest.get("scope_id") != scope_id:
            raise ExtractError("release_invalid", "Only accepted matching scopes may publish")
        _identifier(manifest.get("run_id"))
        relative = f"releases/{release_id}/manifest.json"
        destination = self._safe(self.output_root / relative, self.output_root)
        if destination.exists():
            existing = self.load_release(release_id)
            if existing["scope_id"] != scope_id:
                raise ExtractError("release_invalid", "Release ID belongs to another scope")
            manifest = existing
        else:
            if destination.parent.exists():
                raise ExtractError("release_unavailable", "Incomplete release directory exists")
            # Finalize the pair as one directory. A crash during preparation leaves
            # only a private orphan, never a canonical manifest lacking its digest.
            releases = destination.parent.parent
            _mkdir(releases)
            prepared = releases / f".prepared-{release_id}-{uuid.uuid4().hex}"
            _mkdir(prepared)
            payload = _json_bytes(manifest)
            checksum = hashlib.sha256(payload).hexdigest().encode() + b"\n"
            self._atomic(prepared / "manifest.sha256", checksum)
            self._atomic(prepared / "manifest.json", payload)
            _sync_dir(prepared)
            _check_path(destination.parent)
            os.replace(prepared, destination.parent)
            _sync_dir(releases)
        content = _read_bytes(destination)
        pointer = {
            "release_id": release_id,
            "scope_id": scope_id,
            "manifest": relative,
            "manifest_sha256": hashlib.sha256(content).hexdigest(),
            "run_id": manifest["run_id"],
        }
        self._atomic(self.raw_root / "current" / f"{scope_id}.json", _json_bytes(pointer))
        return pointer

    def recover(self) -> list[dict]:
        """Reconcile publication truth without deleting any interrupted-run evidence."""
        current_dir = self._safe(self.raw_root / "current", self.raw_root)
        if not current_dir.exists():
            return []
        recovered = []
        for path in sorted(current_dir.glob("*.json")):
            current = self.read_current(path.stem)
            run_id = _identifier(current["run_id"])
            result_path = self.output_root / "runs" / run_id / "result.json"
            try:
                result = _decode(_read_bytes(self._safe(result_path, self.output_root)))
            except FileNotFoundError:
                result = {}
            if (
                result.get("status") in {"published", "unchanged"}
                and result.get("accepted_release_id") == current["release_id"]
            ):
                continue
            report = {
                "run_id": run_id,
                "status": "published",
                "scope_id": current["scope_id"],
                "accepted_release_id": current["release_id"],
                "recovered_from_current_pointer": True,
                "manifest": current["manifest"],
            }
            self.write_run(run_id, "recovery.json", report)
            recovered.append(report)
        return recovered

    def find_cached(self, source_identity_digest: str) -> dict | None:
        path = self.raw_root / "acquisition_index" / f"{_digest(source_identity_digest)}.json"
        try:
            return _decode(_read_bytes(self._safe(path, self.raw_root)))
        except FileNotFoundError:
            return None

    def cache(self, source_identity_digest: str, entry: dict) -> None:
        path = self.raw_root / "acquisition_index" / f"{_digest(source_identity_digest)}.json"
        self._atomic(self._safe(path, self.raw_root), _json_bytes(entry))
