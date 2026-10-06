"""Read-only release selection and verification; never infer publication from a file pointer."""

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

import psycopg

from factored_bank.etl.common import database_kwargs, digest_file, stable_digest
from factored_bank.etl.contracts import ORDER, REFERENCES, TABLES, VERSION


class ProfileError(Exception):
    """Safe public error; the message is a fixed code, never source data."""

    def __init__(self, code, exit_code=4):
        super().__init__(code)
        self.code = code
        self.exit_code = exit_code


def valid_id(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def current_release():
    """Pin one PostgreSQL publication using a single read-only snapshot statement."""
    try:
        with psycopg.connect(**database_kwargs()) as pg:
            pg.execute("SET TRANSACTION READ ONLY")
            row = pg.execute(
                "SELECT r.release_id,r.manifest FROM bank.current_release c "
                "JOIN bank.releases r USING(release_id) WHERE c.singleton"
            ).fetchone()
        if not row:
            raise ProfileError("no_published_release", 3)
        return row
    except psycopg.Error:
        raise ProfileError("publication_lookup_failed", 5) from None
    except (OSError, ValueError):
        raise ProfileError("publication_configuration_unavailable", 5) from None


def select_release(release, data_root, lookup=None):
    publication = "not_checked"
    published_manifest = None
    if release == "current":
        release, published_manifest = (lookup or current_release)()
        publication = "confirmed_at_selection"
    if not valid_id(release):
        raise ProfileError("invalid_release_id", 2)
    root = Path(data_root).resolve()
    directory = root / "releases" / release
    if (root / "releases").is_symlink() or directory.is_symlink():
        raise ProfileError("unsafe_release_path")
    if not directory.is_dir():
        raise ProfileError("curated_release_missing", 3)
    manifest, checksum = verify_source(directory)
    if publication == "confirmed_at_selection" and manifest != published_manifest:
        raise ProfileError("publication_manifest_mismatch")
    return directory, manifest, checksum, publication


def _count(value):
    if type(value) is not int or value < 0:
        raise ProfileError("invalid_manifest_count")
    return value


def verify_source(directory):
    """Verify manifest identity, complete membership and accepted-file checksums.

    Rejected and auxiliary files receive size/path checks only. Their contents are
    not profiled; rejection counts and overlapping reasons come from the manifest.
    """
    directory = Path(directory)
    path = directory / "manifest.json"
    if path.is_symlink() or not path.is_file():
        raise ProfileError("manifest_missing_or_unsafe")
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ProfileError("manifest_too_large")
    try:
        raw = path.read_bytes()
        manifest = json.loads(raw)
        identity = {
            k: v for k, v in manifest.items() if k not in ("release_id", "created_at", "provenance")
        }
        if (
            not valid_id(manifest["release_id"])
            or manifest["release_id"] != directory.name
            or stable_digest(identity) != directory.name
        ):
            raise ProfileError("manifest_identity_mismatch")
        if manifest["contract_version"] != VERSION:
            raise ProfileError("unsupported_source_contract")
        if not valid_id(manifest["raw_release_id"]):
            raise ProfileError("invalid_raw_release_id")
        if manifest["source_kind"] not in ("organizer_synthetic", "team_generated_fixture"):
            raise ProfileError("unsupported_source_kind")
        if set(manifest["tables"]) != set(ORDER):
            raise ProfileError("incomplete_table_manifest")
        for table in ORDER:
            info = manifest["tables"][table]
            counts = [_count(info[k]) for k in ("input", "accepted", "rejected")]
            if counts[0] != counts[1] + counts[2] or info["key"] != TABLES[table]["key"]:
                raise ProfileError("manifest_reconciliation_failed")
            for field, maximum in (("reasons", counts[2]), ("quality_flags", counts[1])):
                if not isinstance(info[field], dict):
                    raise ProfileError("invalid_manifest_counts")
                for value in info[field].values():
                    if _count(value) > maximum:
                        raise ProfileError("invalid_manifest_counts")
        expected = {f"{t}{suffix}.parquet" for t in ORDER for suffix in ("", ".rejects")}
        auxiliary = {
            "ml/" + name
            for name in (
                "policies.jsonl",
                "intent_cases.jsonl",
                "retrieval_cases.jsonl",
                "handoff_cases.jsonl",
                "contract.json",
                "taxonomy.json",
                "manifest.json",
                "README.md",
            )
        }
        members = set()
        for entry in manifest["files"]:
            name = entry["path"]
            if name not in expected | auxiliary or name in members:
                raise ProfileError("invalid_release_membership")
            members.add(name)
            member = directory / name
            if member.is_symlink() or (name.startswith("ml/") and member.parent.is_symlink()):
                raise ProfileError("unsafe_member_path")
            if not member.is_file() or member.stat().st_size != _count(entry["size"]):
                raise ProfileError("missing_or_changed_member")
            if not valid_id(entry["sha256"]):
                raise ProfileError("invalid_member_checksum")
            if name in {f"{t}.parquet" for t in ORDER}:
                if digest_file(member) != entry["sha256"]:
                    raise ProfileError("accepted_file_checksum_mismatch")
        if not expected.issubset(members):
            raise ProfileError("incomplete_release_membership")
        return manifest, hashlib.sha256(raw).hexdigest()
    except ProfileError:
        raise
    except (KeyError, TypeError, ValueError, OSError, AttributeError):
        raise ProfileError("malformed_profile_source") from None


def safe_reason_counts(table, counts):
    """Release metadata is also untrusted: emit only recognized rule names."""
    allowed = {
        "duplicate_identity",
        "partition_mismatch",
        "product_customer_mismatch",
        "interaction_customer_mismatch",
    }
    for col in TABLES[table]["columns"]:
        allowed.update(
            f"{rule}:{col['name']}"
            for rule in ("required", "type", "length", "decimal_scale", "duplicate_unique")
        )
    allowed.update("unresolved_reference:" + ref[0] for ref in REFERENCES.get(table, []))
    return {
        "counts": {key: counts[key] for key in sorted(counts) if key in allowed},
        "suppressed_rule_count": sum(key not in allowed for key in counts),
        "suppressed_rule_occurrences": sum(n for key, n in counts.items() if key not in allowed),
    }


def safe_provenance(manifest):
    producer = manifest.get("provenance", {})
    if not isinstance(producer, dict):
        raise ProfileError("invalid_provenance")
    result = {
        key: producer.get(key) if valid_id(producer.get(key)) else None
        for key in ("source_tree_digest", "dependency_lock_digest")
    }
    revision = producer.get("code_revision")
    result["code_revision"] = (
        revision
        if isinstance(revision, str) and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision)
        else None
    )
    as_of = manifest.get("source_as_of")
    try:
        as_of = datetime.fromisoformat(as_of).isoformat() if as_of is not None else None
    except (TypeError, ValueError):
        raise ProfileError("invalid_source_as_of") from None
    return {"producer": result, "source_as_of": as_of}
