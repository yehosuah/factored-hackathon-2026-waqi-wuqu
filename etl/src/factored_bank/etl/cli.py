"""End-to-end execution, offline processing and a restart-safe container scheduler."""

import argparse
import json
import os
import signal
import time
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

from factored_bank.extract.pipeline import ExtractPipeline
from factored_bank.extract.provenance import fingerprint
from factored_bank.extract.source import DEFAULT_BUCKET, S3Source

from .common import atomic_json, now, run_lock
from .contracts import VERSION
from .load import publish, record_run
from .transform import prepare, verify_release


def _ml_root(value):
    if not value.strip():
        raise argparse.ArgumentTypeError("ML pack path must not be empty")
    return Path(value)


def parser():
    p = argparse.ArgumentParser(description="Audited ETL publication and container scheduling")
    p.add_argument("action", choices=("run", "serve", "prepare", "publish", "verify", "status"))
    p.add_argument(
        "--raw-root", type=Path, default=Path(os.getenv("ETL_RAW_ROOT", "data/raw/organizer"))
    )
    p.add_argument(
        "--extract-root", type=Path, default=Path(os.getenv("ETL_EXTRACT_ROOT", "outputs/extract"))
    )
    p.add_argument(
        "--output-root", type=Path, default=Path(os.getenv("ETL_OUTPUT_ROOT", "data/processed"))
    )
    p.add_argument(
        "--ml-root",
        type=_ml_root,
        default=os.getenv("ETL_ML_ROOT"),
        help="Include an ML review pack (default: ETL_ML_ROOT if set, otherwise none)",
    )
    p.add_argument("--manifest", type=Path)
    p.add_argument("--release-dir", type=Path)
    p.add_argument(
        "--offline", action="store_true", default=os.getenv("ETL_OFFLINE", "false") == "true"
    )
    p.add_argument("--interval", type=int, default=int(os.getenv("ETL_INTERVAL_SECONDS", "300")))
    return p


def _extract(args, reconcile):
    descriptor = {
        "kind": "s3",
        "bucket": os.getenv("ETL_BUCKET", DEFAULT_BUCKET),
        "prefix": os.getenv("ETL_PREFIX", "data/"),
        "region": os.getenv("AWS_REGION", "us-east-2"),
    }
    source = (
        SimpleNamespace(descriptor=descriptor)
        if args.offline
        else S3Source(
            bucket=descriptor["bucket"],
            prefix=descriptor["prefix"],
            region=descriptor["region"],
            profile=os.getenv("AWS_PROFILE"),
        )
    )
    pipeline = ExtractPipeline(source, args.raw_root, args.extract_root)
    result = pipeline.verify(scope="full") if args.offline else pipeline.run(scope="full")
    if result["exit_code"]:
        raise RuntimeError(result.get("error_code") or "extract_failed")
    if reconcile and not args.offline:
        verified = pipeline.verify(scope="full", release_id=result["accepted_release_id"])
        if verified["exit_code"]:
            raise RuntimeError("daily_raw_verification_failed")
    return Path(result["manifest_path"])


def run_once(args):
    run = {
        "run_id": uuid4().hex,
        "started_at": now(),
        "status": "running",
        "phase": "extract",
        "release_id": None,
        "error_code": None,
        "contract_version": VERSION,
        "provenance": fingerprint(),
        "operation_mode": "offline" if args.offline else "live_s3",
    }
    args.output_root.mkdir(parents=True, exist_ok=True)
    with run_lock(args.output_root):
        atomic_json(args.output_root / "status.json", run)
        try:
            record_run(run)
            state_path = args.output_root / "scheduler.json"
            state = json.loads(state_path.read_text()) if state_path.is_file() else {}
            reconcile = time.time() - state.get("last_reconciliation", 0) >= 86400
            manifest_path = args.manifest if args.manifest else _extract(args, reconcile)
            run["phase"] = "transform"
            atomic_json(args.output_root / "status.json", run)
            record_run(run)
            directory, manifest = prepare(
                manifest_path, args.raw_root, args.output_root, args.ml_root
            )
            run.update(phase="load", release_id=manifest["release_id"])
            atomic_json(args.output_root / "status.json", run)
            record_run(run)
            result = publish(directory)
            run.update(status="succeeded", phase="complete", finished_at=now(), result=result)
            if reconcile:
                atomic_json(state_path, {"last_reconciliation": time.time()})
        except Exception as exc:
            known = {
                "raw_content_mismatch",
                "database_reconciliation_failed",
                "extract_failed",
                "daily_raw_verification_failed",
                "incomplete_raw_scope",
                "unaccepted_raw_manifest",
            }
            run.update(
                status="failed",
                finished_at=now(),
                error_code=str(exc) if str(exc) in known else type(exc).__name__,
            )
        atomic_json(args.output_root / "runs" / run["run_id"] / "result.json", run)
        atomic_json(args.output_root / "status.json", run)
        try:
            record_run(run)
        except Exception:
            run["monitoring_database_unavailable"] = True
        return run


def serve(args):
    if args.interval < 1:
        raise ValueError("invalid_interval")
    stop = Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    while not stop.is_set():
        started = time.monotonic()
        try:
            result = run_once(args)
        except Exception as exc:
            result = {"status": "failed", "error_code": type(exc).__name__}
        print(json.dumps(result, sort_keys=True), flush=True)
        # No overlaps or burst catch-up after long work; daily reconciliation advances on success.
        stop.wait(max(1, args.interval - (time.monotonic() - started)))
    return 0


def main(argv=None):
    os.umask(0o077)
    try:
        args = parser().parse_args(argv)
        if args.action == "serve":
            return serve(args)
        if args.action == "run":
            result = run_once(args)
        elif args.action == "status":
            result = json.loads((args.output_root / "status.json").read_text())
        elif args.action == "prepare":
            if not args.manifest:
                raise ValueError("manifest_required")
            with run_lock(args.output_root):
                directory, manifest = prepare(
                    args.manifest, args.raw_root, args.output_root, args.ml_root
                )
            result = {
                "status": "prepared",
                "release_id": manifest["release_id"],
                "directory": str(directory),
                "counts": manifest["tables"],
            }
        else:
            if not args.release_dir:
                raise ValueError("release_directory_required")
            if args.action == "publish":
                with run_lock(args.output_root):
                    result = publish(args.release_dir)
            else:
                manifest = verify_release(args.release_dir)
                result = {"status": "verified", "release_id": manifest["release_id"]}
        print(json.dumps(result, sort_keys=True))
        return 1 if result.get("status") == "failed" else 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_code": type(exc).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
