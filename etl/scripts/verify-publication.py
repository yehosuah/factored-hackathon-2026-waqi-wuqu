"""Exercise transaction rollback and repeat publication in an isolated Compose database."""

import json
import subprocess
import sys
from pathlib import Path


def inside():
    import csv
    import hashlib
    import io
    import shutil
    from unittest.mock import patch
    from uuid import uuid4

    import psycopg

    from factored_bank.etl.common import database_kwargs
    from factored_bank.etl.contracts import REFERENCES, TABLES
    from factored_bank.etl.load import publish
    from factored_bank.etl.transform import prepare, verify_release
    from factored_bank.extract.contracts import HEADERS, ROOT_TABLES
    from factored_bank.extract.pipeline import ExtractPipeline

    class Source:
        descriptor = {
            "kind": "team-fixture",
            "bucket": "publication-check",
            "prefix": "data/",
            "region": "us-east-2",
        }

        def __init__(self):
            self.files = {}

        def list_objects(self):
            return [
                {
                    "key": key,
                    "size": len(payload),
                    "etag": hashlib.sha256(payload).hexdigest(),
                    "last_modified": "2026-10-01T00:00:00+00:00",
                }
                for key, payload in sorted(self.files.items())
            ]

        def download(self, obj, destination):
            content = self.files[obj["key"]]
            Path(destination).write_bytes(content)
            return {
                "sha256": hashlib.sha256(content).hexdigest(),
                "size": len(content),
                "version_id": None,
                "remote_checksum": {"status": "unavailable"},
                "attempts": 1,
            }

    data = {}
    for t, spec in TABLES.items():
        row = {}
        for col in spec["columns"]:
            typ = col["type"]
            value = "fixture"
            if not col["required"]:
                value = ""
            elif typ == "BOOLEAN":
                value = "true"
            elif typ == "DATE":
                value = "2023-06-17"
            elif typ == "TIMESTAMP":
                value = "2023-06-17 10:00:00"
            elif typ == "TIME":
                value = "09:00:00"
            elif typ == "INTEGER" or typ.startswith("DECIMAL"):
                value = "1"
            row[col["name"]] = value
        row[spec["key"][0]] = t + "-1"
        data[t] = row
    for t, refs in REFERENCES.items():
        for field, parent, key, _ in refs:
            data[t][field] = data[parent][key]
    for row in data.values():
        if "currency" in row:
            row["currency"] = "USD"

    source = Source()

    def update_source():
        for t, row in data.items():
            out = io.StringIO(newline="")
            w = csv.DictWriter(out, fieldnames=HEADERS[t])
            w.writeheader()
            w.writerow(row)
            key = (
                f"data/{t}.csv"
                if t in ROOT_TABLES
                else f"data/{t}/year=2023/month=06/day=17/{t}_20230617.csv"
            )
            source.files[key] = out.getvalue().encode()

    root = Path("/state/processed/validation") / uuid4().hex
    root.mkdir(parents=True, mode=0o700)
    kwargs = {**database_kwargs(), "dbname": "factored_validation"}
    try:
        update_source()
        pipeline = ExtractPipeline(source, root / "raw", root / "extract", workers=1)
        result = pipeline.run()
        assert result["exit_code"] == 0
        first_dir, first = prepare(result["manifest_path"], root / "raw", root / "prepared")
        assert all(t["accepted"] == 1 for t in first["tables"].values())
        assert publish(first_dir, kwargs)["reused"] is False
        assert publish(first_dir, kwargs)["reused"] is True
        data["products"]["current_balance"] = "2.00"
        update_source()
        changed = pipeline.run()
        assert changed["exit_code"] == 0
        second_dir, second = prepare(changed["manifest_path"], root / "raw", root / "prepared")
        assert first["release_id"] != second["release_id"]
        call_count = 0

        def failure_after_copy(path):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise ValueError("controlled_precommit_failure")
            return verify_release(path)

        with patch("factored_bank.etl.load.verify_release", failure_after_copy):
            try:
                publish(second_dir, kwargs)
            except ValueError as exc:
                assert str(exc) == "controlled_precommit_failure"
            else:
                raise AssertionError("publication_should_fail")
        with psycopg.connect(**kwargs) as pg:
            current = pg.execute(
                "SELECT release_id FROM bank.current_release WHERE singleton"
            ).fetchone()[0]
            assert current == first["release_id"]
            assert (
                pg.execute(
                    "SELECT count(*) FROM bank.releases WHERE release_id=%s",
                    (second["release_id"],),
                ).fetchone()[0]
                == 0
            )
            assert (
                pg.execute(
                    "SELECT count(*) FROM bank.products WHERE release_id=%s",
                    (second["release_id"],),
                ).fetchone()[0]
                == 0
            )
        assert publish(second_dir, kwargs)["reused"] is False
        assert publish(second_dir, kwargs)["reused"] is True
        # An existing but incomplete release must not be accepted as a cached success.
        with psycopg.connect(**kwargs) as pg:
            pg.execute("DELETE FROM bank.products WHERE release_id=%s", (first["release_id"],))
        try:
            publish(first_dir, kwargs)
        except ValueError as exc:
            assert str(exc) == "database_reconciliation_failed"
        else:
            raise AssertionError("incomplete_cached_release_should_fail")
        with psycopg.connect(**kwargs) as pg:
            assert (
                pg.execute(
                    "SELECT release_id FROM bank.current_release WHERE singleton"
                ).fetchone()[0]
                == second["release_id"]
            )
        return {
            "status": "verified",
            "data_source": "isolated_team_generated_fixtures",
            "checks": [
                "all_table_reconciliation",
                "committed_repeat_reuses_rows",
                "correction_new_release",
                "precommit_failure_preserves_current",
                "partial_rows_rolled_back",
                "recovery_publication",
                "incomplete_cached_release_rejected",
            ],
        }
    finally:
        shutil.rmtree(root)


def main():
    if "--inside" in sys.argv:
        try:
            print(json.dumps(inside(), sort_keys=True))
            return 0
        except Exception as exc:
            print(json.dumps({"status": "failed", "error_type": type(exc).__name__}))
            return 1
    commands = [
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "factored_admin",
            "-d",
            "postgres",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            "CREATE DATABASE factored_validation OWNER etl_loader",
        ],
        ["docker", "compose", "exec", "-T", "etl", "python", "-", "--inside"],
    ]
    create = subprocess.run(commands[0], text=True, capture_output=True)
    if create.returncode:
        print("Validation database already exists or cannot be created; no database was modified.")
        return 1
    try:
        result = subprocess.run(
            commands[1], input=Path(__file__).read_text(), text=True, capture_output=True
        )
        print(result.stdout.strip())
        return result.returncode
    finally:
        subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "factored_admin",
                "-d",
                "postgres",
                "-c",
                "DROP DATABASE factored_validation WITH (FORCE)",
            ],
            text=True,
            capture_output=True,
            check=True,
        )


if __name__ == "__main__":
    raise SystemExit(main())
