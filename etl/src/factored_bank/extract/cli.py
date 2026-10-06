"""JSON operator interface; manual invocation only, no scheduler."""

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from .errors import ExtractError
from .pipeline import ExtractPipeline
from .source import DEFAULT_BUCKET, S3Source


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # Argument values may be sensitive; return a stable error without echoing them.
        raise ExtractError("invalid_arguments", exit_code=2)


def main(argv=None) -> int:
    parser = _ArgumentParser(
        description="Extract original organizer CSVs into verified raw releases"
    )
    parser.add_argument("action", choices=("plan", "run", "verify"))
    parser.add_argument("--scope", choices=("full", "pilot"), default="full")
    parser.add_argument("--pilot-date", default="2023-06-17")
    parser.add_argument("--raw-root", type=Path, default=Path("data/raw/organizer"))
    parser.add_argument("--output-root", type=Path, default=Path("outputs/extract"))
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--prefix", default="data/")
    parser.add_argument("--region", default="us-east-2")
    parser.add_argument(
        "--profile", help="Named AWS profile; credentials never belong in command arguments"
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--field-limit", type=int, default=16 * 1024 * 1024)
    parser.add_argument(
        "--plan", type=Path, help="Previously persisted plan to revalidate (run only)"
    )
    parser.add_argument("--release-id", help="Specific accepted release to verify offline")
    try:
        args = parser.parse_args(argv)
        if (args.plan and args.action != "run") or (args.release_id and args.action != "verify"):
            raise ExtractError("invalid_argument_combination", exit_code=2)
        if args.action == "verify":
            # Offline verification must not resolve credentials, consult metadata, or call S3.
            source = SimpleNamespace(
                descriptor={
                    "kind": "s3",
                    "bucket": args.bucket,
                    "prefix": args.prefix,
                    "region": args.region,
                }
            )
        else:
            source = S3Source(
                bucket=args.bucket, prefix=args.prefix, region=args.region, profile=args.profile
            )
        pipeline = ExtractPipeline(
            source,
            args.raw_root,
            args.output_root,
            workers=args.workers,
            field_limit=args.field_limit,
        )
        kwargs = {"scope": args.scope, "pilot_date": args.pilot_date}
        if args.action == "run":
            result = pipeline.run(**kwargs, plan_path=args.plan)
        elif args.action == "verify":
            result = pipeline.verify(**kwargs, release_id=args.release_id)
        else:
            result = pipeline.plan(**kwargs)
    except ExtractError as exc:
        result = {"status": "failed", "exit_code": exc.exit_code, "error_code": exc.code}
    except KeyboardInterrupt:
        result = {"status": "failed", "exit_code": 4, "error_code": "interrupted"}
    except Exception as exc:
        result = {
            "status": "failed",
            "exit_code": 4,
            "error_code": "internal_error",
            "error_type": type(exc).__name__,
        }
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in {"objects", "coverage", "error_details"}},
            sort_keys=True,
        )
    )
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
