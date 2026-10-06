"""Run the frozen system suite against a fresh, disposable synthetic demo."""

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import demo

from factored_bank.evaluation import core
from factored_bank.evaluation.core import load_cases, run_metadata, write_report
from factored_bank.evaluation.runtime import (
    DESCRIPTOR,
    DemoRuntime,
    HarnessError,
    git,
    verified_base_inputs,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-path", required=True, type=Path)
    parser.add_argument("--backend-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--port", type=int, default=18022)
    parser.add_argument(
        "--purpose", choices=("development", "acceptance", "regression"), default="development"
    )
    args = parser.parse_args(argv)
    os.umask(0o077)
    runtime, run, cases, directory = None, None, None, None
    results, failure, cleanup_error = [], None, None
    try:
        source = demo.REPOSITORY / "src/factored_bank/evaluation"
        installed = Path(core.__file__).parent
        for path in source.glob("*.py"):
            if (
                hashlib.sha256(path.read_bytes()).digest()
                != hashlib.sha256((installed / path.name).read_bytes()).digest()
            ):
                raise HarnessError("stale_evaluator_install_reinstall_factored_bank")
        suite, checksum = load_cases(demo.REPOSITORY / "evaluation/system-v1/cases.json")
        cases = suite.cases
        base_sha = git(demo.REPOSITORY, "rev-parse", "HEAD")
        dirty = bool(git(demo.REPOSITORY, "status", "--porcelain", "--untracked-files=all"))
        if dirty and args.purpose in ("acceptance", "regression"):
            raise HarnessError("clean_base_required_for_" + args.purpose)
        base_inputs = verified_base_inputs(demo.REPOSITORY, base_sha) if not dirty else None
        runtime = DemoRuntime(demo, args.backend_path, args.backend_sha, args.run_id, args.port)
        directory = demo.REPOSITORY / "outputs/evaluation" / args.run_id
        directory.mkdir(parents=True, mode=0o700)
        run = run_metadata(
            base_sha=base_sha,
            backend_sha=args.backend_sha,
            checksum=checksum,
            adapter=DESCRIPTOR,
            timestamp=datetime.now(UTC).isoformat(),
            run_id=args.run_id,
            count=len(cases),
            purpose=args.purpose,
        )
        run["base_dirty"] = dirty
        run["base_inputs_verified"] = base_inputs is not None
        run["base_input_sha256"] = (
            hashlib.sha256(json.dumps(base_inputs, sort_keys=True).encode()).hexdigest()
            if base_inputs is not None
            else None
        )
        run["harness_status"] = "running"
        run["acceptance_valid"] = False
        write_report(directory, run, results, cases)
        run.update(runtime.start())
        for case in cases:
            results.append(runtime.evaluate(case))
            write_report(directory, run, results, cases, runtime.secrets)
            print(json.dumps({"case_id": case.id, "correct": results[-1]["correct"]}), flush=True)
    except Exception as error:
        # No response, subprocess output or arbitrary exception text may reach reports/logs.
        failure = str(error) if isinstance(error, HarnessError) else type(error).__name__
    finally:
        if runtime:
            try:
                runtime.close()
            except Exception:
                cleanup_error = "runtime_cleanup_failed"
                failure = failure or cleanup_error
        if run:
            run["finished_at"] = datetime.now(UTC).isoformat()
            run["harness_error"] = failure
            run["cleanup_error"] = cleanup_error
            run["manual_cleanup_required"] = cleanup_error is not None
            run["harness_status"] = "failed" if failure else "completed"
            if failure:
                run["acceptance_valid"] = False
            else:
                run["acceptance_valid"] = args.purpose == "acceptance"
            write_report(directory, run, results, cases, runtime.secrets)
            print(
                json.dumps(
                    {
                        "status": "failed" if failure else "complete",
                        "harness_error": failure,
                        "evaluated": len(results),
                        "output": str(directory),
                    }
                )
            )
        else:
            print(json.dumps({"status": "failed", "harness_error": failure}))
    return 1 if failure else 0


if __name__ == "__main__":
    sys.exit(main())
