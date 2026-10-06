"""Manual Extract coordinator: complete raw releases, never transformed rows."""

import hashlib
import json
import resource
import shutil
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .contracts import CONTRACT_VERSION, VALIDATION_VERSION
from .errors import ExtractError
from .inventory import coverage, digest, scope_definition, select_objects
from .provenance import fingerprint
from .storage import RawStore
from .validation import validate_csv


def now() -> str:
    return datetime.now(UTC).isoformat()


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def release_identity(manifest: dict) -> str:
    stable = {
        "scope_id": manifest["scope_id"],
        "source": manifest["source"],
        "scope": manifest["scope"],
        "contract_version": manifest["contract_version"],
        "validation_version": manifest["validation_version"],
        "validation_config": manifest["validation_config"],
        "objects": [],
    }
    for entry in manifest["objects"]:
        stable["objects"].append({k: entry[k] for k in ("source", "sha256", "size", "validation")})
    return digest(stable)


class ExtractPipeline:
    def __init__(
        self,
        source,
        raw_root: Path,
        output_root: Path,
        workers: int = 4,
        field_limit: int = 16 * 1024 * 1024,
    ):
        if not 1 <= workers <= 32 or not 1 <= field_limit <= 1024 * 1024 * 1024:
            raise ExtractError("invalid_limits", exit_code=2)
        self.source = source
        self.descriptor = dict(source.descriptor)
        self.store = RawStore(Path(raw_root), Path(output_root))
        self.raw_root = self.store.raw_root
        self.output_root = self.store.output_root
        self.workers = workers
        self.field_limit = field_limit
        self._accepted_entries: dict[str, dict] = {}

    def _base(self, action: str, scope: str, pilot_date: str) -> dict:
        scope_id, definition = scope_definition(self.descriptor, scope, pilot_date)
        return {
            "result_schema_version": 1,
            "contract_version": CONTRACT_VERSION,
            "validation_version": VALIDATION_VERSION,
            "provenance": fingerprint(),
            "configuration_digest": digest(
                {
                    "source": self.descriptor,
                    "scope": definition,
                    "workers": self.workers,
                    "field_limit": self.field_limit,
                }
            ),
            "run_id": uuid4().hex,
            "action": action,
            "scope_id": scope_id,
            "scope": definition,
            "started_at": now(),
            "status": "failed",
            "exit_code": 4,
            "candidate_release_id": None,
            "accepted_release_id": None,
            "previous_release_id": None,
            "downloaded": 0,
            "reused": 0,
            "failed": 0,
            "not_attempted": 0,
            "expected": 0,
            "expected_bytes": 0,
            "verified_bytes": 0,
            "transferred_bytes": 0,
            "warnings": [],
            "error_code": None,
            "objects": [],
        }

    def _finish(self, result: dict, started: float) -> dict:
        if result["action"] == "run" and not result["objects"] and result.get("plan_path"):
            plan = self.store.read_json_safe(Path(result["plan_path"]))
            result["objects"] = [
                {"key": obj["key"], "status": "not_attempted"} for obj in plan["objects"]
            ]
        result["finished_at"] = now()
        result["duration_seconds"] = round(time.monotonic() - started, 3)
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        result["peak_process_memory_bytes"] = peak if sys.platform == "darwin" else peak * 1024
        result["result_path"] = str(self.output_root / "runs" / result["run_id"] / "result.json")
        self.store.write_run(result["run_id"], "result.json", result)
        return result

    def _error(self, result: dict, exc: Exception) -> None:
        code = exc.code if isinstance(exc, ExtractError) else "internal_error"
        exit_code = exc.exit_code if isinstance(exc, ExtractError) else 4
        result.update(
            status="review_required" if exit_code == 3 else "failed",
            exit_code=exit_code,
            error_code=code,
        )
        # The publication pointer, not a possibly interrupted report, determines commit truth.
        result["error_type"] = type(exc).__name__
        if code == "local_content_unavailable" or (
            result["action"] == "run"
            and result["previous_release_id"] is None
            and result["status"] == "failed"
        ):
            result["status"] = "unavailable"
        if isinstance(exc, ExtractError) and exc.details:
            result["error_details"] = exc.details

    def _list(self, definition: dict) -> tuple[list[dict], dict]:
        started = now()
        objects = select_objects(self.source.list_objects(), self.descriptor, definition)
        return objects, {"started_at": started, "finished_at": now()}

    def _current(self, scope_id: str) -> dict | None:
        current = self.store.read_current(scope_id)
        if current:
            manifest = current["manifest_data"]
            if manifest["release_id"] != release_identity(manifest):
                raise ExtractError("manifest_identity_mismatch")
            return manifest
        return None

    def _cache_id(self, obj: dict) -> str:
        return digest({"source": self.descriptor, "object": obj})

    def _cached(self, obj: dict) -> dict | None:
        identity = self._cache_id(obj)
        # Accepted manifests are authoritative; the index is only an optimization.
        if identity in self._accepted_entries:
            return self._accepted_entries[identity]
        return self.store.find_cached(identity)

    def _make_plan(
        self, result: dict, objects: list[dict], window: dict, previous: dict | None
    ) -> dict:
        self._accepted_entries = (
            {self._cache_id(entry["source"]): entry for entry in previous["objects"]}
            if previous
            else {}
        )
        previous_keys = {x["source"]["key"] for x in previous["objects"]} if previous else set()
        missing = sorted(previous_keys - {x["key"] for x in objects})
        plan = {
            "plan_schema_version": 1,
            "run_id": result["run_id"],
            "source": self.descriptor,
            "scope_id": result["scope_id"],
            "scope": result["scope"],
            "contract_version": CONTRACT_VERSION,
            "validation_version": VALIDATION_VERSION,
            "validation_config": {"field_limit": self.field_limit},
            "listing_window": window,
            "objects": objects,
            "coverage": coverage(objects),
            "previous_release_id": previous["release_id"] if previous else None,
            "blockers": [{"code": "source_object_disappeared", "keys": missing}] if missing else [],
        }
        plan["inventory_digest"] = digest(objects)
        result.update(
            expected=len(objects),
            expected_bytes=sum(x["size"] for x in objects),
            not_attempted=len(objects),
            previous_release_id=plan["previous_release_id"],
        )
        result["coverage"] = plan["coverage"]
        result["warnings"] = ["upstream_completeness_unproven", "source_business_cutoff_unknown"]
        if any(v["missing_date_ranges"] for v in plan["coverage"].values()):
            result["warnings"].append("calendar_gaps")
        reuse_bytes = 0
        for obj in objects:
            cached = self._cached(obj)
            if cached:
                path = self.store.object_path(cached["sha256"])
                if path.is_file() and path.stat().st_size == obj["size"]:
                    reuse_bytes += obj["size"]
        plan["estimated_reuse_bytes"] = reuse_bytes
        plan["estimated_download_bytes"] = result["expected_bytes"] - reuse_bytes
        path = self.store.write_run(result["run_id"], "plan.json", plan)
        result["plan_path"] = str(path)
        result["estimated_reuse_bytes"] = reuse_bytes
        result["estimated_download_bytes"] = plan["estimated_download_bytes"]
        return plan

    def plan(self, scope: str = "full", pilot_date: str = "2023-06-17") -> dict:
        started = time.monotonic()
        result = self._base("plan", scope, pilot_date)
        with ExitStack() as stack:
            try:
                stack.enter_context(self.store.lock())
                result["recovery"] = self.store.recover()
                previous = self._current(result["scope_id"])
                objects, window = self._list(result["scope"])
                plan = self._make_plan(result, objects, window, previous)
                if plan["blockers"]:
                    raise ExtractError(
                        "source_object_disappeared",
                        exit_code=3,
                        details={"blockers": plan["blockers"]},
                    )
                result.update(status="planned", exit_code=0)
            except Exception as exc:
                self._error(result, exc)
            return self._finish(result, started)

    def _acquire(self, obj: dict, run_id: str) -> tuple[dict, str]:
        cached = self._cached(obj)
        checked_at = now()
        if cached and cached.get("source") == obj:
            path = self.store.object_path(cached["sha256"])
            if (
                path.is_file()
                and path.stat().st_size == obj["size"]
                and file_hash(path) == cached["sha256"]
            ):
                validation = validate_csv(path, obj["table"], field_limit=self.field_limit)
                entry = {**cached, "validation": validation, "checked_at": checked_at}
                return entry, "reused"
        if shutil.disk_usage(self.raw_root).free < obj["size"] + 16 * 1024**2:
            raise ExtractError("insufficient_disk_space")
        stage = self.store.staging_path(run_id, digest(obj["key"]))
        try:
            downloaded = self.source.download(obj, stage)
        except ExtractError as exc:
            if cached and cached.get("source") == obj:
                raise ExtractError(
                    "local_content_unavailable",
                    details={"acquisition_error": exc.code, **exc.details},
                ) from None
            raise
        sha = file_hash(stage)
        size = stage.stat().st_size
        if size != obj["size"] or sha != downloaded["sha256"] or size != downloaded["size"]:
            raise ExtractError("download_integrity_mismatch")
        local = self.store.install(stage, sha)
        path = self.store.object_path(sha)
        try:
            validation = validate_csv(path, obj["table"], field_limit=self.field_limit)
        except ExtractError as exc:
            exc.details = {
                **exc.details,
                "local_path": local,
                "sha256": sha,
                "received_bytes": size,
                "transferred_bytes": downloaded.get("transferred_bytes", size),
            }
            raise
        entry = {
            "source": obj,
            "table": obj["table"],
            "partition_date": obj["partition_date"],
            "sha256": sha,
            "local_path": local,
            "size": size,
            "version_id": downloaded.get("version_id"),
            "remote_checksum": downloaded.get("remote_checksum", {"status": "unavailable"}),
            "validation": validation,
            "ingested_at": cached["ingested_at"] if cached else checked_at,
            "checked_at": now(),
            "attempts": downloaded.get("attempts", 1),
            "transferred_bytes": downloaded.get("transferred_bytes", size),
        }
        self.store.cache(self._cache_id(obj), entry)
        return entry, "downloaded"

    def _acquire_all(self, objects: list[dict], result: dict) -> list[dict]:
        entries = []
        errors = []
        iterator = iter(objects)
        dispositions = {}
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            pending = {}

            def submit():
                obj = next(iterator, None)
                if obj:
                    pending[executor.submit(self._acquire, obj, result["run_id"])] = obj

            for _ in range(self.workers):
                submit()
            while pending:
                completed, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in completed:
                    obj = pending.pop(future)
                    try:
                        entry, disposition = future.result()
                        entries.append(entry)
                        result[disposition] += 1
                        result["verified_bytes"] += entry["size"]
                        if disposition == "downloaded":
                            result["transferred_bytes"] += entry.get(
                                "transferred_bytes", entry["size"]
                            )
                        dispositions[obj["key"]] = {
                            "key": obj["key"],
                            "status": disposition,
                            "sha256": entry["sha256"],
                            "attempts": entry.get("attempts", 1)
                            if disposition == "downloaded"
                            else 0,
                            "transferred_bytes": entry.get("transferred_bytes", entry["size"])
                            if disposition == "downloaded"
                            else 0,
                        }
                    except Exception as exc:
                        errors.append(exc)
                        result["failed"] += 1
                        item = {
                            "key": obj["key"],
                            "status": "failed",
                            "error_code": exc.code
                            if isinstance(exc, ExtractError)
                            else "internal_error",
                            "error_type": type(exc).__name__,
                        }
                        if isinstance(exc, ExtractError):
                            item["details"] = exc.details
                            result["transferred_bytes"] += exc.details.get("transferred_bytes", 0)
                        dispositions[obj["key"]] = item
                if not errors:
                    for _ in completed:
                        submit()
        result["not_attempted"] = len(objects) - len(dispositions)
        result["objects"] = [
            dispositions.get(x["key"], {"key": x["key"], "status": "not_attempted"})
            for x in objects
        ]
        self.store.write_run(result["run_id"], "diagnostics.json", {"objects": result["objects"]})
        if errors:
            raise errors[0]
        return sorted(entries, key=lambda x: x["source"]["key"])

    def run(
        self, scope: str = "full", pilot_date: str = "2023-06-17", plan_path: Path | None = None
    ) -> dict:
        started = time.monotonic()
        result = self._base("run", scope, pilot_date)
        with ExitStack() as stack:
            try:
                stack.enter_context(self.store.lock())
                result["recovery"] = self.store.recover()
                previous = self._current(result["scope_id"])
                objects, window = self._list(result["scope"])
                plan = self._make_plan(result, objects, window, previous)
                if plan_path:
                    try:
                        supplied = json.loads(Path(plan_path).read_text())
                        consistent = (
                            supplied["scope_id"] == plan["scope_id"]
                            and supplied["source"] == plan["source"]
                            and supplied["contract_version"] == CONTRACT_VERSION
                            and supplied["validation_version"] == VALIDATION_VERSION
                            and supplied["validation_config"] == plan["validation_config"]
                            and supplied["objects"] == objects
                            and supplied["inventory_digest"] == digest(objects)
                        )
                    except (OSError, ValueError, KeyError, TypeError) as exc:
                        raise ExtractError("invalid_plan", exit_code=2) from exc
                    if not consistent:
                        raise ExtractError("stale_plan", exit_code=3)
                if plan["blockers"]:
                    raise ExtractError(
                        "source_object_disappeared",
                        exit_code=3,
                        details={"blockers": plan["blockers"]},
                    )
                if (
                    shutil.disk_usage(self.raw_root).free
                    < result["estimated_download_bytes"] + 64 * 1024**2
                ):
                    raise ExtractError("insufficient_disk_space")
                provenance = result["provenance"]
                entries = self._acquire_all(objects, result)
                final_objects, final_window = self._list(result["scope"])
                if final_objects != objects:
                    raise ExtractError("source_inventory_changed", exit_code=3)
                if fingerprint()["source_tree_digest"] != provenance["source_tree_digest"]:
                    raise ExtractError("code_changed_during_run", exit_code=3)
                zero_rows = [
                    e["source"]["key"] for e in entries if e["validation"]["row_count"] == 0
                ]
                if zero_rows:
                    result["warnings"].append("zero_row_files")
                manifest = {
                    "manifest_schema_version": 1,
                    "status": "accepted",
                    "run_id": result["run_id"],
                    "scope_id": result["scope_id"],
                    "scope": result["scope"],
                    "source": self.descriptor,
                    "contract_version": CONTRACT_VERSION,
                    "validation_version": VALIDATION_VERSION,
                    "validation_config": {"field_limit": self.field_limit},
                    "created_at": now(),
                    "source_as_of": None,
                    "provenance": provenance,
                    "configuration_digest": result["configuration_digest"],
                    "listing_window": window,
                    "final_listing_window": final_window,
                    "inventory_digest": digest(objects),
                    "objects": entries,
                    "coverage": plan["coverage"],
                    "zero_row_files": zero_rows,
                    "warnings": result["warnings"],
                }
                release_id = release_identity(manifest)
                manifest["release_id"] = release_id
                result["candidate_release_id"] = release_id
                manifest_path = self.output_root / "releases" / release_id / "manifest.json"
                if previous and previous["release_id"] == release_id:
                    result["status"] = "unchanged"
                else:
                    if manifest_path.exists():
                        manifest = self.store.load_release(release_id)
                        if release_identity(manifest) != release_id:
                            raise ExtractError("manifest_identity_mismatch")
                    self.store.publish(manifest, result["scope_id"])
                    result["status"] = "published"
                result.update(
                    exit_code=0,
                    accepted_release_id=release_id,
                    manifest_path=str(manifest_path),
                    logical_rows=sum(x["validation"]["row_count"] for x in entries),
                    table_rows={
                        table: sum(
                            x["validation"]["row_count"] for x in entries if x["table"] == table
                        )
                        for table in plan["coverage"]
                    },
                )
            except Exception as exc:
                self._error(result, exc)
                # Commit may have succeeded just before a storage/reporting exception.
                if result["candidate_release_id"]:
                    try:
                        current = self._current(result["scope_id"])
                        if current and current["release_id"] == result["candidate_release_id"]:
                            result["accepted_release_id"] = current["release_id"]
                            result["publication_committed"] = True
                    except Exception:
                        pass
            return self._finish(result, started)

    def verify(
        self, release_id: str | None = None, scope: str = "full", pilot_date: str = "2023-06-17"
    ) -> dict:
        started = time.monotonic()
        result = self._base("verify", scope, pilot_date)
        with ExitStack() as stack:
            try:
                stack.enter_context(self.store.lock())
                # An explicit historical release does not depend on current pointers.
                if release_id is None:
                    self.store.recover()
                manifest = (
                    self.store.load_release(release_id)
                    if release_id
                    else self._current(result["scope_id"])
                )
                if not manifest:
                    raise ExtractError("release_unavailable")
                if (
                    manifest["source"] != self.descriptor
                    or manifest["scope_id"] != result["scope_id"]
                ):
                    raise ExtractError("release_scope_mismatch", exit_code=2)
                if manifest["release_id"] != release_identity(manifest):
                    raise ExtractError("manifest_identity_mismatch")
                if (
                    manifest["contract_version"] != CONTRACT_VERSION
                    or manifest["validation_version"] != VALIDATION_VERSION
                ):
                    raise ExtractError("contract_version_mismatch", exit_code=3)
                source_objects = [x["source"] for x in manifest["objects"]]
                if (
                    select_objects(source_objects, self.descriptor, result["scope"])
                    != source_objects
                ):
                    raise ExtractError("invalid_release_inventory")
                if digest(source_objects) != manifest["inventory_digest"]:
                    raise ExtractError("manifest_inventory_mismatch")
                for entry in manifest["objects"]:
                    if (
                        entry["table"] != entry["source"]["table"]
                        or entry["partition_date"] != entry["source"]["partition_date"]
                    ):
                        raise ExtractError("manifest_object_metadata_mismatch")
                    path = self.store.object_path(entry["sha256"])
                    if (
                        not path.is_file()
                        or path.stat().st_size != entry["size"]
                        or entry["size"] != entry["source"]["size"]
                        or entry["local_path"] != str(path.relative_to(self.raw_root))
                        or file_hash(path) != entry["sha256"]
                    ):
                        raise ExtractError("local_content_corrupt")
                    validation = validate_csv(
                        path,
                        entry["table"],
                        field_limit=manifest["validation_config"]["field_limit"],
                    )
                    if validation != entry["validation"]:
                        raise ExtractError("validation_evidence_mismatch")
                    result["verified_bytes"] += entry["size"]
                    result["reused"] += 1
                result.update(
                    status="verified",
                    exit_code=0,
                    accepted_release_id=manifest["release_id"],
                    expected=len(manifest["objects"]),
                    expected_bytes=sum(x["size"] for x in manifest["objects"]),
                    logical_rows=sum(x["validation"]["row_count"] for x in manifest["objects"]),
                    manifest_path=str(
                        self.output_root / "releases" / manifest["release_id"] / "manifest.json"
                    ),
                )
            except Exception as exc:
                self._error(result, exc)
                result["status"] = "unavailable"
            return self._finish(result, started)
