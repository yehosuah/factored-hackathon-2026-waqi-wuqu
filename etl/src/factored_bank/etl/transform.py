"""Lossless lineage, typed validation and atomic Parquet release preparation."""

import hashlib
import json
import os
import re
import shutil
import stat
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import duckdb

from factored_bank.extract.inventory import scope_definition
from factored_bank.extract.pipeline import release_identity
from factored_bank.extract.provenance import fingerprint

from .common import atomic_json, digest_file, now, stable_digest, sync_path
from .contracts import CONTRACT, ORDER, REFERENCES, TABLES, VERSION
from .contracts import identifier as q

META = {
    "_source_sha256": "VARCHAR",
    "_source_row": "BIGINT",
    "_process_partition": "DATE",
    "_ingested_at": "TIMESTAMPTZ",
}


def _literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def verify_release(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "manifest.json").read_text())
    identity = dict(manifest)
    for name in ("release_id", "created_at", "provenance"):
        identity.pop(name, None)
    if (
        stable_digest(identity) != manifest["release_id"]
        or directory.name != manifest["release_id"]
    ):
        raise ValueError("curated_manifest_identity_mismatch")
    for entry in manifest["files"]:
        path = (directory / entry["path"]).resolve()
        if not path.is_relative_to(directory) or path.is_symlink():
            raise ValueError("unsafe_curated_path")
        if path.stat().st_size != entry["size"] or digest_file(path) != entry["sha256"]:
            raise ValueError("curated_content_mismatch")
    return manifest


def _validation(columns, key):
    errors = []
    for col in columns:
        name, typ = col["name"], col["type"]
        f = "r." + q(name)
        tests = []
        if col["required"]:
            tests.append((f"{f} IS NULL OR trim({f})=''", "required:" + name))
        if typ not in ("TEXT",) and not typ.startswith("VARCHAR"):
            tests.append((f"{f} IS NOT NULL AND TRY_CAST({f} AS {typ}) IS NULL", "type:" + name))
        if typ.startswith("VARCHAR"):
            limit = int(re.search(r"\d+", typ)[0])
            tests.append((f"length({f})>{limit}", "length:" + name))
        if typ.startswith("DECIMAL"):
            scale = int(typ.split(",")[1].rstrip(")"))
            pattern = rf"[+-]?[0-9]+(\.[0-9]{{1,{scale}}})?"
            tests.append(
                (
                    f"{f} IS NOT NULL AND NOT regexp_full_match({f}, {_literal(pattern)})",
                    "decimal_scale:" + name,
                )
            )
        if col["unique"]:
            tests.append(
                (
                    f"{f} IS NOT NULL AND count(*) OVER(PARTITION BY {f})>1",
                    "duplicate_unique:" + name,
                )
            )
        errors.extend(f"CASE WHEN {test} THEN {_literal(reason)} END" for test, reason in tests)
    parts = ",".join("r." + q(f) for f in key)
    errors.append(f"CASE WHEN count(*) OVER(PARTITION BY {parts})>1 THEN 'duplicate_identity' END")
    if "process_date" in key:
        errors.append(
            "CASE WHEN TRY_CAST(r.process_date AS DATE) IS DISTINCT FROM "
            "r._process_partition THEN 'partition_mismatch' END"
        )
    return errors


def prepare(raw_manifest_path, raw_root, output_root, ml_root=None):
    """Prepare all tables. No database pointer changes until the separate load succeeds."""
    raw_manifest_path, raw_root = Path(raw_manifest_path), Path(raw_root).resolve()
    output_root = Path(output_root)
    raw = json.loads(raw_manifest_path.read_text())
    if raw.get("status") != "accepted" or raw["release_id"] != release_identity(raw):
        raise ValueError("unaccepted_raw_manifest")
    full_scope_id, full_scope = scope_definition(raw["source"], "full", "2023-06-17")
    if (
        raw.get("scope") != full_scope
        or raw.get("scope_id") != full_scope_id
        or set(o["table"] for o in raw["objects"]) != set(TABLES)
    ):
        raise ValueError("incomplete_raw_scope")
    for obj in raw["objects"]:
        path = (raw_root / obj["local_path"]).resolve()
        if not path.is_relative_to(raw_root) or not path.is_file():
            raise ValueError("unsafe_or_missing_raw_object")
        if path.stat().st_size != obj["size"] or digest_file(path) != obj["sha256"]:
            raise ValueError("raw_content_mismatch")
    provenance = fingerprint()
    ml_identity = _ml_identity(ml_root)
    input_identity = stable_digest(
        {
            "raw_release": raw["release_id"],
            "contract": CONTRACT,
            "code": provenance["source_tree_digest"],
            "lock": provenance["dependency_lock_digest"],
            "ml": ml_identity,
        }
    )
    cache = output_root / "prepared" / f"{input_identity}.json"
    if cache.is_file():
        cached = json.loads(cache.read_text())
        release = output_root / "releases" / cached["release_id"]
        return release, verify_release(release)
    stage = output_root / "staging" / uuid4().hex
    stage.mkdir(parents=True, mode=0o700)
    db_path = stage / "work.duckdb"
    c = duckdb.connect(str(db_path))
    c.execute("SET threads=4")
    c.execute("SET memory_limit='1GB'")
    result = {
        "contract_version": VERSION,
        "input_identity": input_identity,
        "raw_release_id": raw["release_id"],
        "raw_manifest_sha256": digest_file(raw_manifest_path),
        "source_kind": "organizer_synthetic"
        if raw["source"]["kind"] == "s3"
        else "team_generated_fixture",
        "source": raw["source"],
        "source_as_of": raw["source_as_of"],
        "timezone": CONTRACT["timezone"],
        "readiness": "exploration_ready",
        "tables": {},
        "files": [],
        "ml": {},
    }
    try:
        for table in ORDER:
            definition = TABLES[table]
            names = [x["name"] for x in definition["columns"]]
            schema = ",".join(q(n) + " VARCHAR" for n in names)
            schema += "," + ",".join(q(n) + " " + typ for n, typ in META.items())
            c.execute(f"CREATE TABLE raw_{table} ({schema})")
            entries = sorted(
                (o for o in raw["objects"] if o["table"] == table),
                key=lambda o: (o["source"]["key"], o["sha256"]),
            )
            for obj in entries:
                path = (raw_root / obj["local_path"]).resolve()
                if not path.is_relative_to(raw_root) or not path.is_file():
                    raise ValueError("unsafe_or_missing_raw_object")
                cols = ",".join(q(n) for n in names)
                c.execute(
                    f"INSERT INTO raw_{table} SELECT {cols}, ?, row_number() OVER(), "
                    "?::DATE, ?::TIMESTAMPTZ FROM read_csv(?, header=true, all_varchar=true, "
                    "nullstr='', delim=',', quote='\"', escape='\"', parallel=false, "
                    "strict_mode=true, max_line_size=16777216)",
                    [obj["sha256"], obj["partition_date"], obj["ingested_at"], str(path)],
                )
                if digest_file(path) != obj["sha256"]:
                    raise ValueError("raw_content_mismatch")
            expected = sum(o["validation"]["row_count"] for o in entries)
            received = c.execute(f"SELECT count(*) FROM raw_{table}").fetchone()[0]
            if expected != received:
                raise ValueError("raw_row_count_mismatch")
            errors = _validation(definition["columns"], definition["key"])
            flags = []
            for field, parent, parent_key, advisory in REFERENCES.get(table, []):
                test = f"r.{q(field)} IS NOT NULL AND NOT EXISTS(SELECT 1 FROM {parent} p "
                test += f"WHERE p.{q(parent_key)}=r.{q(field)}"
                if "process_date" in TABLES[parent]["key"]:
                    test += " AND p.process_date=TRY_CAST(r.process_date AS DATE)"
                test += ")"
                dest = flags if advisory else errors
                dest.append(
                    f"CASE WHEN {test} THEN {_literal('unresolved_reference:' + field)} END"
                )
            if table == "transactions":
                errors.append(
                    "CASE WHEN NOT EXISTS(SELECT 1 FROM products p WHERE "
                    "p.product_id=r.product_id AND p.customer_id=r.customer_id) "
                    "THEN 'product_customer_mismatch' END"
                )
            if table in ("call_transcripts", "satisfaction_surveys", "complaints"):
                field = "origin_interaction_id" if table == "complaints" else "interaction_id"
                errors.append(
                    f"CASE WHEN r.{field} IS NOT NULL AND NOT EXISTS(SELECT 1 "
                    f"FROM call_center_interactions p WHERE p.interaction_id=r.{field} "
                    "AND p.process_date=TRY_CAST(r.process_date AS DATE) "
                    "AND p.customer_id=r.customer_id) THEN 'interaction_customer_mismatch' END"
                )
            if table == "complaints":
                errors.append(
                    "CASE WHEN r.affected_product_id IS NOT NULL AND NOT EXISTS(SELECT 1 "
                    "FROM products p WHERE p.product_id=r.affected_product_id AND "
                    "p.customer_id=r.customer_id) THEN 'product_customer_mismatch' END"
                )
            c.execute(
                f"CREATE TABLE checked_{table} AS SELECT r.*, "
                f"list_filter([{','.join(errors)}], x -> x IS NOT NULL) AS _errors, "
                f"list_filter([{','.join(flags) if flags else 'NULL::VARCHAR'}], "
                f"x -> x IS NOT NULL) AS _quality_flags FROM raw_{table} r"
            )
            projection = ",".join(
                f"TRY_CAST({q(x['name'])} AS {x['type']}) AS {q(x['name'])}"
                for x in definition["columns"]
            )
            meta = ",".join(q(n) for n in META)
            c.execute(
                f"CREATE TABLE {table} AS SELECT {projection},{meta},_quality_flags "
                f"FROM checked_{table} WHERE len(_errors)=0"
            )
            accepted = c.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            rejected = c.execute(
                f"SELECT count(*) FROM checked_{table} WHERE len(_errors)>0"
            ).fetchone()[0]
            if received != accepted + rejected:
                raise ValueError("transform_reconciliation_failed")
            reasons = dict(
                c.execute(
                    f"SELECT reason,count(*) FROM checked_{table}, "
                    "unnest(_errors) u(reason) GROUP BY reason"
                ).fetchall()
            )
            advisory_counts = dict(
                c.execute(
                    f"SELECT flag,count(*) FROM {table}, "
                    "unnest(_quality_flags) u(flag) GROUP BY flag"
                ).fetchall()
            )
            result["tables"][table] = {
                "input": received,
                "accepted": accepted,
                "rejected": rejected,
                "reasons": reasons,
                "quality_flags": advisory_counts,
                "key": definition["key"],
            }
            order = ",".join(q(n) for n in definition["key"])
            _export(c, f"SELECT * FROM {table} ORDER BY {order}", stage, table + ".parquet", result)
            _export(
                c,
                f"SELECT * FROM checked_{table} WHERE len(_errors)>0 "
                "ORDER BY _source_sha256,_source_row",
                stage,
                table + ".rejects.parquet",
                result,
            )
            c.execute(f"DROP TABLE raw_{table}")
            c.execute(f"DROP TABLE checked_{table}")
        _copy_ml(ml_root, stage, result)
        if _ml_identity(ml_root) != ml_identity:
            raise ValueError("ml_source_changed_during_preparation")
    except BaseException:
        c.close()
        shutil.rmtree(stage)
        raise
    c.close()
    db_path.unlink(missing_ok=True)
    db_path.with_suffix(".duckdb.wal").unlink(missing_ok=True)
    result["release_id"] = stable_digest(result)
    result["created_at"] = now()
    result["provenance"] = provenance
    atomic_json(stage / "manifest.json", result)
    destination = output_root / "releases" / result["release_id"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        verify_release(destination)
        shutil.rmtree(stage)
    else:
        os.rename(stage, destination)
        sync_path(destination.parent)
    atomic_json(cache, {"release_id": result["release_id"]})
    return destination, verify_release(destination)


def _export(c, query, stage, name, manifest):
    path = stage / name
    c.execute(f"COPY ({query}) TO {_literal(path)} (FORMAT PARQUET, COMPRESSION ZSTD)")
    os.chmod(path, 0o600)
    sync_path(path)
    manifest["files"].append(
        {"path": name, "size": path.stat().st_size, "sha256": digest_file(path)}
    )


_ML_AUXILIARY_FILES = ("contract.json", "taxonomy.json", "manifest.json", "README.md")
_ML_DATA_FILES = (
    "policies.jsonl",
    "intent_cases.jsonl",
    "retrieval_cases.jsonl",
    "handoff_cases.jsonl",
)


def _ml_source(root, name):
    """Validate a pack member before reading it, without following symlinks."""
    root = Path(root).resolve()
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("unsafe_ml_source_path")
    source = root
    for part in relative.parts:
        source = source / part
        if source.is_symlink():
            raise ValueError("unsafe_ml_source_path")
    if not source.resolve().is_relative_to(root) or not source.is_file():
        raise ValueError("unsafe_ml_source_path")
    return source


@contextmanager
def _open_ml_source(root, name):
    """Pin directories and reject symlink/special-file swaps at the kernel boundary."""
    root = Path(root).resolve()
    _ml_source(root, name)
    parts = (*root.parts[1:], *Path(name).parts)
    directory = os.open(root.anchor, os.O_RDONLY | os.O_DIRECTORY)
    descriptor = None
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(
            parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("unsafe_ml_source_path")
        stream = os.fdopen(descriptor, "rb")
        descriptor = None
        with stream:
            yield stream
    except OSError as error:
        raise ValueError("unsafe_ml_source_path") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory)


def _ml_digest(root, name):
    digest = hashlib.sha256()
    with _open_ml_source(root, name) as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ml_identity(root):
    if root is None:
        return None
    root = Path(root)
    # Enforce safety before hashing or reusing an already prepared release.
    for name in _ML_AUXILIARY_FILES:
        _ml_source(root, name)
    return {
        p.name: _ml_digest(root, p.name)
        for p in sorted(root.iterdir())
        if (p.suffix in (".jsonl", ".json") or p.name == "README.md") and p.is_file()
    }


def _copy_ml(root, stage, manifest):
    if root is None:
        manifest["ml"] = {"readiness": "not_included"}
        return
    root = Path(root)
    with _open_ml_source(root, "manifest.json") as source:
        manifest_bytes = source.read()
    source_manifest = json.loads(manifest_bytes)
    if source_manifest.get("source_kind") != "team_synthetic":
        raise ValueError("unexpected_ml_source_kind")
    members = {f["path"]: f for f in source_manifest["files"]}
    # The manifest itself is pinned by the release identity; it cannot checksum itself.
    required_members = {*_ML_DATA_FILES, *_ML_AUXILIARY_FILES} - {"manifest.json"}
    if len(members) != len(source_manifest["files"]) or not required_members <= members.keys():
        raise ValueError("ml_source_membership_mismatch")
    target = stage / "ml"
    target.mkdir(mode=0o700)
    # Copy through pinned file descriptors, then validate and parse these exact bytes.
    # Reopening source paths for validation could inspect a different file after a swap.
    for name, entry in members.items():
        if name not in required_members:
            with _open_ml_source(root, name) as source:
                size = os.fstat(source.fileno()).st_size
            if size != entry["bytes"] or _ml_digest(root, name) != entry["sha256"]:
                raise ValueError("ml_source_content_mismatch")
            continue
        destination = target / name
        with _open_ml_source(root, name) as source, destination.open("wb") as output:
            shutil.copyfileobj(source, output)
        os.chmod(destination, 0o600)
        if (
            destination.stat().st_size != entry["bytes"]
            or digest_file(destination) != entry["sha256"]
        ):
            raise ValueError("ml_source_content_mismatch")
    (target / "manifest.json").write_bytes(manifest_bytes)
    os.chmod(target / "manifest.json", 0o600)
    source_contract = json.loads((target / "contract.json").read_text())
    if source_contract.get("scored_evaluation_authorized") is not False:
        raise ValueError("ml_review_contract_changed")
    taxonomy = json.loads((target / "taxonomy.json").read_text())
    label_ids = {label["id"] for label in taxonomy["labels"]}
    documents = set()
    counts = {}
    for name in _ML_DATA_FILES:
        records = [
            json.loads(line) for line in (target / name).read_text().splitlines() if line.strip()
        ]
        if not records:
            raise ValueError("empty_ml_dataset")
        key = "document_id" if name == "policies.jsonl" else "example_id"
        if len({r[key] for r in records}) != len(records):
            raise ValueError("duplicate_ml_identity")
        if any(
            r["source_kind"] != "team_synthetic" or r["language"] not in ("es", "pt")
            for r in records
        ):
            raise ValueError("invalid_ml_provenance")
        if len(records) != members[name]["record_count"]:
            raise ValueError("ml_record_reconciliation_failed")
        if name == "policies.jsonl":
            documents = {r["document_id"] for r in records}
        elif name == "intent_cases.jsonl":
            if any(set(r["candidate_intents"]) - label_ids for r in records):
                raise ValueError("unknown_ml_intent")
        else:
            field = (
                "candidate_relevant_document_ids"
                if name == "retrieval_cases.jsonl"
                else "candidate_relevant_policy_ids"
            )
            if any(set(r[field]) - documents for r in records):
                raise ValueError("unknown_ml_policy_reference")
        counts[name] = len(records)
    for name in (*_ML_DATA_FILES, *_ML_AUXILIARY_FILES):
        destination = target / name
        if destination.suffix == ".json":
            json.loads(destination.read_text())
        sync_path(destination)
        manifest["files"].append(
            {
                "path": "ml/" + name,
                "size": destination.stat().st_size,
                "sha256": digest_file(destination),
            }
        )
    manifest["ml"] = {
        "readiness": "exploration_ready",
        "source_kind": "team_synthetic",
        "approval_status": "draft_review_only",
        "scored_evaluation_authorized": False,
        "counts": counts,
        "source_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "limitations": [
            "Labels, policies and ES/PT translations require review",
            "No independent held-out benchmark is asserted",
        ],
    }
    sync_path(target)
