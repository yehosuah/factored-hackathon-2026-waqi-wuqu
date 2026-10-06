"""Load a portable release in an independent directory and trace source evidence privately."""

import csv
import json
import shutil
import tempfile
from pathlib import Path

import duckdb

from factored_bank.etl.common import digest_file
from factored_bank.etl.contracts import ORDER, TABLES
from factored_bank.etl.transform import verify_release


def main():
    pointer = json.loads(Path("data/processed/current.json").read_text())
    release_id = pointer["release_id"]
    source = Path("data/processed/releases") / release_id
    with tempfile.TemporaryDirectory(prefix="consumer-", dir="outputs") as tmp:
        portable = Path(tmp) / release_id
        shutil.copytree(source, portable)
        manifest = verify_release(portable)
        counts = {}
        c = duckdb.connect()
        try:
            for table in ORDER:
                path = portable / (table + ".parquet")
                n = c.execute("SELECT count(*) FROM read_parquet(?)", [str(path)]).fetchone()[0]
                reject = c.execute(
                    "SELECT count(*) FROM read_parquet(?)",
                    [str(portable / (table + ".rejects.parquet"))],
                ).fetchone()[0]
                declared = manifest["tables"][table]
                assert n == declared["accepted"] and reject == declared["rejected"]
                assert n + reject == declared["input"]
                counts[table] = n
            key = TABLES["customers"]["key"][0]
            identity, checksum, ordinal = c.execute(
                f'SELECT "{key}",_source_sha256,_source_row FROM read_parquet(?) LIMIT 1',
                [str(portable / "customers.parquet")],
            ).fetchone()
            raw_manifest = json.loads(
                (
                    Path("outputs/extract/releases") / manifest["raw_release_id"] / "manifest.json"
                ).read_text()
            )
            entry = next(
                o
                for o in raw_manifest["objects"]
                if o["table"] == "customers" and o["sha256"] == checksum
            )
            raw_path = Path("data/raw/organizer") / entry["local_path"]
            assert digest_file(raw_path) == checksum
            csv.field_size_limit(16 * 1024 * 1024)
            with raw_path.open(newline="", encoding="utf-8-sig") as f:
                for index, record in enumerate(csv.DictReader(f), start=1):
                    if index == ordinal:
                        assert record[key] == identity
                        break
                else:
                    raise AssertionError("source_record_missing")
            for name, n in manifest["ml"]["counts"].items():
                assert (
                    len(
                        [
                            line
                            for line in (portable / "ml" / name).read_text().splitlines()
                            if line.strip()
                        ]
                    )
                    == n
                )
            print(
                json.dumps(
                    {
                        "status": "verified",
                        "release_id": release_id,
                        "accepted_rows": sum(counts.values()),
                        "input_rows": sum(t["input"] for t in manifest["tables"].values()),
                        "rejected_rows": sum(t["rejected"] for t in manifest["tables"].values()),
                        "checks": [
                            "independent_directory_load",
                            "all_table_and_reject_counts",
                            "source_checksum_and_record_trace",
                            "ml_record_counts",
                            "portable_checksums",
                        ],
                        "ml": manifest["ml"],
                    },
                    sort_keys=True,
                )
            )
        finally:
            c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
