"""Transactional PostgreSQL release publication; simulator state is a separate schema."""

import duckdb
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from .common import atomic_json, database_kwargs, now
from .contracts import ORDER, TABLES, VERSION
from .transform import META, verify_release


def initialize(connection):
    if not connection.execute("SELECT 1 FROM pg_namespace WHERE nspname='bank'").fetchone():
        connection.execute("CREATE SCHEMA bank")
    connection.execute("CREATE TABLE IF NOT EXISTS bank.contract (version text PRIMARY KEY)")
    versions = [r[0] for r in connection.execute("SELECT version FROM bank.contract").fetchall()]
    if versions and versions != [VERSION]:
        raise ValueError("incompatible_database_contract")
    connection.execute("INSERT INTO bank.contract VALUES(%s) ON CONFLICT DO NOTHING", (VERSION,))
    connection.execute(
        "CREATE TABLE IF NOT EXISTS bank.releases (release_id text PRIMARY KEY, "
        "manifest jsonb NOT NULL, published_at timestamptz NOT NULL DEFAULT now())"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS bank.current_release (singleton boolean PRIMARY KEY "
        "DEFAULT true CHECK(singleton), release_id text NOT NULL REFERENCES bank.releases)"
    )
    connection.execute(
        "CREATE TABLE IF NOT EXISTS bank.etl_runs (run_id text PRIMARY KEY, "
        "started_at timestamptz NOT NULL, finished_at timestamptz, status text NOT NULL, "
        "release_id text, error_code text, phase text NOT NULL)"
    )
    for table in ORDER:
        cols = [
            sql.SQL("{} {}").format(sql.Identifier(x["name"]), sql.SQL(x["type"]))
            for x in TABLES[table]["columns"]
        ]
        cols.extend(sql.SQL("{} {}").format(sql.Identifier(n), sql.SQL(t)) for n, t in META.items())
        cols.append(sql.SQL("_quality_flags text[] NOT NULL"))
        key = sql.SQL(",").join(sql.Identifier(k) for k in ["release_id", *TABLES[table]["key"]])
        connection.execute(
            sql.SQL(
                "CREATE TABLE IF NOT EXISTS bank.{} (release_id text NOT NULL "
                "REFERENCES bank.releases, {}, PRIMARY KEY ({}))"
            ).format(sql.Identifier(table), sql.SQL(",").join(cols), key)
        )
        if any(x["name"] == "customer_id" for x in TABLES[table]["columns"]):
            connection.execute(
                sql.SQL(
                    "CREATE INDEX IF NOT EXISTS {} ON bank.{} (release_id, customer_id)"
                ).format(sql.Identifier(table + "_customer_idx"), sql.Identifier(table))
            )
    if connection.execute("SELECT 1 FROM pg_roles WHERE rolname='backend_api'").fetchone():
        connection.execute("REVOKE ALL ON ALL TABLES IN SCHEMA bank FROM backend_api")
        connection.execute(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA bank REVOKE ALL ON TABLES FROM backend_api"
        )
        connection.execute(
            "GRANT SELECT ON bank.contract,bank.releases,bank.current_release,"
            "bank.etl_runs,bank.products,bank.transactions TO backend_api"
        )
        connection.execute("GRANT SELECT(customer_id,release_id) ON bank.customers TO backend_api")


def publish(directory, db_kwargs=None):
    manifest = verify_release(directory)
    release_id = manifest["release_id"]
    c = duckdb.connect(":memory:")
    c.execute("SET TimeZone='UTC'")
    try:
        with psycopg.connect(**(db_kwargs or database_kwargs())) as pg:
            pg.execute("SELECT pg_advisory_xact_lock(7236148201)")
            initialize(pg)
            exists = pg.execute(
                "SELECT manifest FROM bank.releases WHERE release_id=%s", (release_id,)
            ).fetchone()
            if exists:
                if exists[0] != manifest:
                    raise ValueError("database_release_identity_conflict")
            else:
                pg.execute(
                    "INSERT INTO bank.releases(release_id, manifest) VALUES(%s,%s)",
                    (release_id, Jsonb(manifest)),
                )
                for table in ORDER:
                    fields = (
                        [x["name"] for x in TABLES[table]["columns"]]
                        + list(META)
                        + ["_quality_flags"]
                    )
                    projection = ",".join(
                        'CAST("_ingested_at" AS VARCHAR) AS "_ingested_at"'
                        if n == "_ingested_at"
                        else '"' + n + '"'
                        for n in fields
                    )
                    rows = c.execute(
                        f"SELECT {projection} FROM read_parquet(?)",
                        [str(directory / (table + ".parquet"))],
                    )
                    copy = sql.SQL("COPY bank.{} ({}) FROM STDIN").format(
                        sql.Identifier(table),
                        sql.SQL(",").join(sql.Identifier(n) for n in ["release_id", *fields]),
                    )
                    with pg.cursor().copy(copy) as stream:
                        while batch := rows.fetchmany(5000):
                            for row in batch:
                                stream.write_row((release_id, *row))
            # Reconcile cached database releases too, before accepting their reuse.
            for table in ORDER:
                count = pg.execute(
                    sql.SQL("SELECT count(*) FROM bank.{} WHERE release_id=%s").format(
                        sql.Identifier(table)
                    ),
                    (release_id,),
                ).fetchone()[0]
                if count != manifest["tables"][table]["accepted"]:
                    raise ValueError("database_reconciliation_failed")
            # The file layer must still be intact at commit, including a reused release.
            verify_release(directory)
            pg.execute(
                "INSERT INTO bank.current_release(singleton,release_id) VALUES(true,%s) "
                "ON CONFLICT(singleton) DO UPDATE SET release_id=excluded.release_id",
                (release_id,),
            )
        # Repairable mirror, never the authority used by the backend.
        atomic_json(
            directory.parent.parent / "current.json",
            {"release_id": release_id, "published_at": now()},
        )
        return {
            "status": "published",
            "release_id": release_id,
            "reused": bool(exists),
            "counts": {t: m["accepted"] for t, m in manifest["tables"].items()},
        }
    finally:
        c.close()


def record_run(run, db_kwargs=None):
    with psycopg.connect(**(db_kwargs or database_kwargs())) as pg:
        initialize(pg)
        pg.execute(
            "INSERT INTO bank.etl_runs(run_id,started_at,finished_at,status,"
            "release_id,error_code,phase) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(run_id) DO UPDATE SET "
            "finished_at=excluded.finished_at,status=excluded.status,release_id=excluded.release_id,"
            "error_code=excluded.error_code,phase=excluded.phase",
            tuple(
                run.get(k)
                for k in (
                    "run_id",
                    "started_at",
                    "finished_at",
                    "status",
                    "release_id",
                    "error_code",
                    "phase",
                )
            ),
        )
