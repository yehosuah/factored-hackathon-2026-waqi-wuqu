"""Generate a complete, verified Extract release from invented card-support rows."""

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path

from factored_bank.etl.common import atomic_json
from factored_bank.etl.contracts import REFERENCES, TABLES
from factored_bank.extract.contracts import HEADERS, ROOT_TABLES
from factored_bank.extract.pipeline import ExtractPipeline


class DemoSource:
    descriptor = {
        "kind": "team-fixture",
        "bucket": "factored-local-demo",
        "prefix": "data/",
        "region": "us-east-2",
    }

    def __init__(self, revision=1):
        self.files = {}
        for table, records in demo_rows(revision).items():
            content = io.StringIO(newline="")
            writer = csv.DictWriter(content, fieldnames=HEADERS[table])
            writer.writeheader()
            writer.writerows(records)
            key = (
                f"data/{table}.csv"
                if table in ROOT_TABLES
                else f"data/{table}/year=2023/month=06/day=17/{table}_20230617.csv"
            )
            self.files[key] = content.getvalue().encode()

    def list_objects(self):
        return [
            {
                "key": key,
                "size": len(content),
                "etag": hashlib.sha256(content).hexdigest(),
                "last_modified": "2026-10-04T00:00:00+00:00",
            }
            for key, content in sorted(self.files.items())
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


def demo_rows(revision=1):
    if revision not in (1, 2):
        raise ValueError("invalid_demo_revision")
    data = {}
    for table, definition in TABLES.items():
        row = {}
        for column in definition["columns"]:
            typ = column["type"]
            value = "demo"
            if not column["required"]:
                value = ""
            elif typ == "BOOLEAN":
                value = "true"
            elif typ == "DATE":
                value = "2023-06-17"
            elif typ == "TIMESTAMP":
                value = "2023-06-17 10:00:00"
            elif typ == "TIME":
                value = "10:00:00"
            elif typ == "INTEGER" or typ.startswith("DECIMAL"):
                value = "1"
            row[column["name"]] = value
        row[definition["key"][0]] = "DEMO-" + table[:8].upper() + "-001"
        data[table] = [row]
    data["customers"][0].update(
        customer_id="TEAM-CUSTOMER-001",
        document_type="DNI",
        document_number="DEMO-DOC-001",
        customer_status="Active",
    )
    data["products"][0].update(
        product_id="DEMO-CARD-001",
        product_type="Tarjeta Crédito",
        product_status="Active",
        product_number="DEMO-TEST-4242",
        currency="USD",
        current_balance="125.50" if revision == 1 else "126.50",
        credit_limit="1000.00",
    )
    data["branches"][0]["branch_code"] = "DEMO-B01"
    data["service_agents"][0].update(
        agent_id="DEMO-AGENT-001",
        employee_code="DEMO-EMP-001",
        agent_type="Digital",
        experience_level="Specialist",
        languages="Español,Portugués",
        specialty="Fraudes",
        agent_status="Active",
        avg_csat="4.50",
    )
    for table, references in REFERENCES.items():
        for field, parent, key, _ in references:
            data[table][0][field] = data[parent][0][key]
    data["transactions"][0].update(currency="USD", amount="12.50", transaction_status="Completed")
    data["complaints"][0]["currency"] = "USD"
    data["call_transcripts"][0]["detected_language"] = "es"
    for table, overrides in {
        "customers": {"customer_id": "DEMO-CUSTOMER-OTHER", "document_number": "DEMO-DOC-OTHER"},
        "products": {
            "product_id": "DEMO-CARD-OTHER",
            "customer_id": "DEMO-CUSTOMER-OTHER",
            "product_number": "DEMO-TEST-9999",
        },
    }.items():
        data[table].append({**data[table][0], **overrides})
    template = data["transactions"][0]
    data["transactions"] = [
        {**template, "transaction_id": f"DEMO-TX-{index:03}", "amount": amount}
        for index, amount in enumerate(("12.50", "8.00", "5.25"), 1)
    ]
    return data


def generate(raw_root, extract_root, revision=1):
    raw_root, extract_root = Path(raw_root), Path(extract_root)
    marker = extract_root / "team-demo.json"
    if marker.is_file():
        if json.loads(marker.read_text()) != {"source": DemoSource.descriptor}:
            raise ValueError("existing_state_is_not_team_demo")
    else:
        for root in (raw_root, extract_root):
            if root.exists() and any(root.iterdir()):
                raise ValueError("refuse_nonempty_unmarked_demo_state")
        extract_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        atomic_json(marker, {"source": DemoSource.descriptor})
    pipeline = ExtractPipeline(DemoSource(revision), raw_root, extract_root, workers=1)
    result = pipeline.run(scope="full")
    if result["exit_code"]:
        raise ValueError("demo_extract_failed")
    verified = pipeline.verify(scope="full")
    if verified["exit_code"]:
        raise ValueError("demo_extract_verification_failed")
    manifest = json.loads(Path(result["manifest_path"]).read_text())
    atomic_json(extract_root / "demo-manifest.json", manifest)
    return {
        "status": "verified",
        "data_source": "team_generated_fixture",
        "revision": revision,
        "raw_release_id": manifest["release_id"],
        "objects": len(manifest["objects"]),
        "rows": verified["logical_rows"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", required=True, type=Path)
    parser.add_argument("--extract-root", required=True, type=Path)
    parser.add_argument("--revision", type=int, default=1, choices=(1, 2))
    args = parser.parse_args(argv)
    os.umask(0o077)
    print(json.dumps(generate(args.raw_root, args.extract_root, args.revision)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
