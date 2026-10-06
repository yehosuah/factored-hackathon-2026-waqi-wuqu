"""Human-readable operator CLI with stable, sanitized failure codes."""

import argparse
import json
import os
import sys
from pathlib import Path

from factored_bank.etl.common import atomic_json

from .core import profile_release
from .source import ProfileError


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ProfileError("invalid_arguments", 2)


def _output_path(output_root, data_root, release_id):
    output = Path(output_root)
    # Do not follow output directory symlinks, including existing ancestors.
    if any(p.is_symlink() for p in (output, *output.absolute().parents)):
        raise ProfileError("unsafe_output_path", 6)
    directory = output.resolve() / release_id
    protected = [
        Path(data_root).resolve(),
        Path(os.getenv("ETL_RAW_ROOT", "data/raw/organizer")).resolve(),
    ]
    if directory.is_symlink() or any(directory.is_relative_to(root) for root in protected):
        raise ProfileError("output_overlaps_source", 6)
    return directory / "profile.json"


def main(argv=None):
    parser = _Parser(
        description="Profile accepted Parquet data without exposing individual records"
    )
    parser.add_argument(
        "--release", required=True, help="Curated release ID, or current (requires PostgreSQL)"
    )
    parser.add_argument(
        "--data-root", type=Path, default=Path(os.getenv("ETL_OUTPUT_ROOT", "data/processed"))
    )
    parser.add_argument("--output-root", type=Path, default=Path("outputs/profiles"))
    try:
        args = parser.parse_args(argv)
        profile = profile_release(args.release, args.data_root)
        provenance = profile["release_provenance"]
        path = _output_path(args.output_root, args.data_root, provenance["release_id"])
        try:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            atomic_json(path, profile)
        except OSError:
            raise ProfileError("profile_write_failed", 6) from None
        totals = {
            key: sum(t[key] for t in profile["reconciliation"].values())
            for key in ("input", "accepted", "rejected")
        }
        print(f"Release: {provenance['release_id']}")
        print(f"Publication: {provenance['publication_status']}")
        print(
            f"Rows: input={totals['input']} accepted={totals['accepted']} "
            f"rejected={totals['rejected']}"
        )
        for table, info in profile["reconciliation"].items():
            print(
                f"  {table}: input={info['input']} accepted={info['accepted']} "
                f"rejected={info['rejected']}"
            )
        cards = profile["card_support"]
        print(f"Card products: {cards['card_product_rows']} / {cards['accepted_product_rows']}")
        print(f"Observed modeling/privacy notices: {len(profile['modeling_risks']['observed'])}")
        print(
            "profile.json written. Metrics describe accepted historical data, "
            "not verified business outcomes."
        )
        return 0
    except ProfileError as exc:
        code, exit_code = exc.code, exc.exit_code
    except KeyboardInterrupt:
        code, exit_code = "profile_interrupted", 1
    except Exception:
        code, exit_code = "profile_failed", 1
    print(
        json.dumps({"status": "failed", "error_code": code, "exit_code": exit_code}),
        file=sys.stderr,
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
