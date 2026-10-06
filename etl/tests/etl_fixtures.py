"""Completely invented contract-valid rows; no organizer records are copied."""

import csv
import io

from test_extract_pipeline import FixtureSource, daily_key

from factored_bank.etl.contracts import REFERENCES, TABLES
from factored_bank.extract.contracts import HEADERS, ROOT_TABLES
from factored_bank.extract.pipeline import ExtractPipeline


def rows():
    data = {}
    for table, definition in TABLES.items():
        row = {}
        for col in definition["columns"]:
            name, typ = col["name"], col["type"]
            if not col["required"]:
                row[name] = ""
            elif typ == "BOOLEAN":
                row[name] = "true"
            elif typ == "INTEGER" or typ.startswith("DECIMAL"):
                row[name] = "1"
            elif typ == "DATE":
                row[name] = "2023-06-17"
            elif typ == "TIMESTAMP":
                row[name] = "2023-06-17 10:00:00"
            elif typ == "TIME":
                row[name] = "09:00:00"
            else:
                row[name] = "fixture"
        row[definition["key"][0]] = table + "-1"
        data[table] = [row]
    for table, refs in REFERENCES.items():
        for field, parent, key, _ in refs:
            data[table][0][field] = data[parent][0][key]
    for table in ("products", "transactions", "complaints"):
        data[table][0]["currency"] = "USD"
    data["products"][0].update(
        product_type="Tarjeta Crédito",
        product_status="Active",
        current_balance="125.50",
        product_number="TEAM-TEST-4242",
    )
    data["customers"][0].update(
        document_type="DNI", document_number="TEAM-DOC-001", customer_status="Active"
    )
    data["branches"][0].update(branch_code="TEAM-B01")
    data["service_agents"][0].update(employee_code="TEAM-EMP-001")
    data["transactions"][0]["amount"] = "12.50"
    data["call_transcripts"][0]["detected_language"] = "es"
    return data


def csv_payload(table, records):
    s = io.StringIO(newline="")
    w = csv.DictWriter(s, fieldnames=HEADERS[table])
    w.writeheader()
    w.writerows(records)
    return s.getvalue().encode()


def raw_release(tmp_path, data=None, extra_daily=None):
    data = data or rows()
    source = FixtureSource()
    source.files = {
        (f"data/{t}.csv" if t in ROOT_TABLES else daily_key(t)): csv_payload(t, rs)
        for t, rs in data.items()
    }
    if extra_daily:
        for table, day, rs in extra_daily:
            source.files[daily_key(table, day)] = csv_payload(table, rs)
    raw = tmp_path / "raw"
    result = ExtractPipeline(source, raw, tmp_path / "extract", workers=1).run()
    assert result["exit_code"] == 0
    return result["manifest_path"], raw
