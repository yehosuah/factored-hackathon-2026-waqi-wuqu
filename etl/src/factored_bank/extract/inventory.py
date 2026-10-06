"""Approved object selection and source coverage without row transformation."""

import hashlib
import json
import re
from datetime import date, timedelta

from .contracts import DAILY_TABLES, HEADERS, ROOT_TABLES
from .errors import ExtractError


def digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def scope_definition(source: dict, mode: str, pilot_date: str) -> tuple[str, dict]:
    if mode not in {"full", "pilot"}:
        raise ExtractError("invalid_scope", exit_code=2)
    try:
        day = date.fromisoformat(pilot_date).isoformat()
    except (ValueError, TypeError) as exc:
        raise ExtractError("invalid_pilot_date", exit_code=2) from exc
    scope = {
        "mode": mode,
        "pilot_date": day if mode == "pilot" else None,
        "tables": sorted(HEADERS),
    }
    return f"{mode}-{digest({'source': source, 'scope': scope})[:24]}", scope


def select_objects(objects: list[dict], source: dict, scope: dict) -> list[dict]:
    prefix = source.get("prefix", "data/")
    selected = []
    seen = set()
    for item in objects:
        key = item.get("key", "")
        if not isinstance(key, str) or not key.startswith(prefix):
            raise ExtractError("invalid_source_listing", exit_code=3)
        relative = key[len(prefix) :]
        top = relative.split("/")[0]
        table = top.split(".")[0]
        if table not in HEADERS:
            continue
        if key.endswith("/") and item.get("size") == 0:
            continue
        partition = None
        if table in ROOT_TABLES:
            if relative != f"{table}.csv":
                raise ExtractError(
                    "unexpected_object_layout", exit_code=3, details={"table": table}
                )
        elif table in DAILY_TABLES:
            match = re.fullmatch(
                rf"{table}/year=(\d{{4}})/month=(\d{{2}})/day=(\d{{2}})/"
                rf"{table}_(\d{{8}})\.csv",
                relative,
            )
            try:
                if not match:
                    raise ValueError
                year, month, day, suffix = match.groups()
                partition = date(int(year), int(month), int(day)).isoformat()
                if suffix != year + month + day:
                    raise ValueError
            except ValueError as exc:
                raise ExtractError(
                    "unexpected_object_layout", exit_code=3, details={"table": table}
                ) from exc
            if scope["mode"] == "pilot" and partition != scope["pilot_date"]:
                continue
        if key in seen:
            raise ExtractError("duplicate_source_key", exit_code=3)
        seen.add(key)
        if (
            not isinstance(item.get("size"), int)
            or item["size"] < 0
            or not isinstance(item.get("etag"), str)
            or not item["etag"]
            or not isinstance(item.get("last_modified"), str)
        ):
            raise ExtractError("invalid_source_metadata", exit_code=3)
        selected.append(
            {
                "key": key,
                "size": item["size"],
                "etag": item["etag"],
                "last_modified": item["last_modified"],
                "table": table,
                "partition_date": partition,
            }
        )
    missing = sorted(set(HEADERS) - {x["table"] for x in selected})
    if missing:
        raise ExtractError("missing_required_tables", exit_code=3, details={"tables": missing})
    return sorted(selected, key=lambda x: x["key"])


def coverage(objects: list[dict]) -> dict:
    result = {}
    for table in sorted(HEADERS):
        items = [x for x in objects if x["table"] == table]
        days = sorted(
            {date.fromisoformat(x["partition_date"]) for x in items if x["partition_date"]}
        )
        gaps = [
            {
                "from": (a + timedelta(days=1)).isoformat(),
                "through": (b - timedelta(days=1)).isoformat(),
                "days": (b - a).days - 1,
            }
            for a, b in zip(days, days[1:], strict=False)
            if (b - a).days > 1
        ]
        result[table] = {
            "objects": len(items),
            "bytes": sum(x["size"] for x in items),
            "first_partition": days[0].isoformat() if days else None,
            "last_partition": days[-1].isoformat() if days else None,
            "missing_date_ranges": gaps,
            "source_as_of": None,
        }
    return result
