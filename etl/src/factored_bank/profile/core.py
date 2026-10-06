"""Deterministic SQL aggregates. No row values or free text cross the interface."""

import tempfile

import duckdb

from factored_bank.etl.common import now
from factored_bank.etl.contracts import ORDER, TABLES
from factored_bank.etl.transform import META
from factored_bank.extract.provenance import fingerprint

from .source import (
    ProfileError,
    safe_provenance,
    safe_reason_counts,
    select_release,
    verify_source,
)
from .vocabulary import CARD_TYPES, DISTRIBUTIONS, EVENTS, LEAKAGE_CANDIDATES


def rate(numerator, denominator):
    return round(numerator / denominator, 8) if denominator else None


def _one(db, sql, parameters=None):
    result = db.execute(sql, parameters or [])
    return dict(zip([col[0] for col in result.description], result.fetchone(), strict=True))


def _distribution(db, table, column, allowed):
    # Identifiers are internal constants. Only reviewed labels are returned to Python.
    field = f'"{column}"'
    allowed = list(allowed)
    rows = db.execute(
        f"SELECT CAST({field} AS VARCHAR),count(*) FROM {table} "
        f"WHERE CAST({field} AS VARCHAR) IN (SELECT unnest(?)) GROUP BY 1 ORDER BY 1",
        [allowed],
    ).fetchall()
    summary = _one(
        db,
        f"""
        SELECT count(*) AS total_rows,
            count(*) FILTER(WHERE {field} IS NULL) AS null_rows,
            count(*) FILTER(WHERE {field} IS NOT NULL AND
                CAST({field} AS VARCHAR) NOT IN (SELECT unnest(?))) AS suppressed_rows,
            count(DISTINCT {field}) FILTER(WHERE
                CAST({field} AS VARCHAR) NOT IN (SELECT unnest(?))) AS suppressed_distinct_values
        FROM {table}
    """,
        [allowed, allowed],
    )
    summary["values"] = [
        {"value": label, "count": n, "share_of_all_rows": rate(n, summary["total_rows"])}
        for label, n in rows
    ]
    shape = _one(
        db,
        f"""
        SELECT count(*) AS distinct_nonnull_values,coalesce(sum(n),0)::BIGINT AS nonnull_rows,
            min(n) AS smallest_group,max(n) AS largest_group
        FROM (SELECT count(*) AS n FROM {table} WHERE {field} IS NOT NULL GROUP BY {field})
    """,
    )
    shape["largest_group_share"] = rate(shape["largest_group"] or 0, shape["nonnull_rows"])
    shape["largest_to_smallest_ratio"] = rate(shape["largest_group"] or 0, shape["smallest_group"])
    summary["class_balance"] = shape
    return summary


def _register_tables(db, directory, manifest):
    tables = {}
    for table in ORDER:
        db.read_parquet(str(directory / f"{table}.parquet")).create_view(table)
        schema = db.execute(f"DESCRIBE {table}").fetchall()
        expected = [(col["name"], col["type"]) for col in TABLES[table]["columns"]]
        expected += list(META.items()) + [("_quality_flags", "VARCHAR[]")]

        def normalize(typ):
            if typ == "TEXT" or typ.startswith("VARCHAR("):
                return "VARCHAR"
            return "TIMESTAMP WITH TIME ZONE" if typ == "TIMESTAMPTZ" else typ.replace(", ", ",")

        if [(x[0], normalize(x[1])) for x in schema] != [(n, normalize(t)) for n, t in expected]:
            raise ProfileError("incompatible_parquet_schema")
        columns = [col["name"] for col in TABLES[table]["columns"]]
        null_sql = ",".join(f'count(*) FILTER(WHERE "{name}" IS NULL)' for name in columns)
        counts = db.execute(f"SELECT count(*),{null_sql} FROM {table}").fetchone()
        n = counts[0]
        if n != manifest["tables"][table]["accepted"]:
            raise ProfileError("accepted_row_count_mismatch")
        keys = ",".join(f'"{key}"' for key in TABLES[table]["key"])
        key_count = db.execute(
            f"SELECT count(*) FROM (SELECT {keys} FROM {table} GROUP BY {keys})"
        ).fetchone()[0]
        tables[table] = {
            "accepted_rows": n,
            "effective_key": TABLES[table]["key"],
            "distinct_effective_keys": key_count,
            "duplicate_excess_rows": n - key_count,
            "columns": {
                col["name"]: {
                    "type": col["type"],
                    "required": col["required"],
                    "null_rows": missing,
                    "null_rate": rate(missing, n),
                }
                for col, missing in zip(TABLES[table]["columns"], counts[1:], strict=True)
            },
            "distributions": {},
        }
        for column, allowed in DISTRIBUTIONS.get(table, {}).items():
            tables[table]["distributions"][column] = _distribution(db, table, column, allowed)
    return tables


def _unique_id(db, table, key):
    n, populated, unique = db.execute(
        f"SELECT count(*),count({key}),count(DISTINCT {key}) FROM {table}"
    ).fetchone()
    return n == populated == unique


def _product_activity(db, tables):
    n = tables["products"]["accepted_rows"]
    counts = dict(
        db.execute(
            "SELECT product_type,count(*) FROM products WHERE product_type "
            "IN (SELECT unnest(?)) GROUP BY 1",
            [list(CARD_TYPES)],
        ).fetchall()
    )
    card_count = sum(counts.values())
    result = {
        "explicit_card_types": list(CARD_TYPES),
        "accepted_product_rows": n,
        "card_product_rows": card_count,
        "card_product_share": rate(card_count, n),
        "by_type": {kind: counts.get(kind, 0) for kind in CARD_TYPES},
    }
    if not _unique_id(db, "products", "product_id"):
        result["transaction_activity"] = {
            "status": "unavailable",
            "reason": "ambiguous_product_identity",
        }
        return result
    coverage = _one(
        db,
        """
        SELECT count(*) AS accepted_transaction_rows,
            count(*) FILTER(WHERE p.product_id IS NULL) AS unmatched_product_rows,
            count(*) FILTER(WHERE p.product_id IS NOT NULL AND
                t.customer_id IS DISTINCT FROM p.customer_id) AS ownership_mismatch_rows,
            count(*) FILTER(WHERE p.product_id IS NOT NULL AND
                t.customer_id=p.customer_id) AS ownership_consistent_rows
        FROM transactions t LEFT JOIN products p ON t.product_id=p.product_id
    """,
    )
    # View DDL cannot bind parameters; quote the reviewed constants only.
    card_types_sql = ",".join("'" + value.replace("'", "''") + "'" for value in CARD_TYPES)
    db.execute(f"""CREATE TEMP VIEW card_transactions AS SELECT t.* FROM transactions t
        JOIN products p ON t.product_id=p.product_id AND t.customer_id=p.customer_id
        WHERE p.product_type IN ({card_types_sql})""")
    count = db.execute("SELECT count(*) FROM card_transactions").fetchone()[0]
    declines = db.execute(
        "SELECT count(*) FROM card_transactions WHERE transaction_status='Declined'"
    ).fetchone()[0]
    result["transaction_activity"] = {
        "status": "available",
        **coverage,
        "card_transaction_rows": count,
        "card_transaction_share": rate(count, coverage["accepted_transaction_rows"]),
        "recorded_card_declines": declines,
        "recorded_card_decline_rate": rate(declines, count),
        "status_distribution": _distribution(
            db,
            "card_transactions",
            "transaction_status",
            DISTRIBUTIONS["transactions"]["transaction_status"],
        ),
    }
    return result


def _text_quality(db):
    result = {}
    for column in ("customer_text", "agent_text", "full_text"):
        stats = _one(
            db,
            f"SELECT count(*) AS accepted_rows,count({column}) AS nonnull_rows,"
            f"count(DISTINCT {column}) AS distinct_exact_texts FROM call_transcripts",
        )
        largest = [
            r[0]
            for r in db.execute(
                f"SELECT count(*) AS n FROM call_transcripts "
                f"WHERE {column} IS NOT NULL GROUP BY {column} ORDER BY n DESC LIMIT 5"
            ).fetchall()
        ]
        stats.update(
            duplicate_excess_rows=stats["nonnull_rows"] - stats["distinct_exact_texts"],
            largest_group_sizes=largest,
            top_five_share=rate(sum(largest), stats["nonnull_rows"]),
        )
        stats["duplicate_excess_rate"] = rate(stats["duplicate_excess_rows"], stats["nonnull_rows"])
        result[column] = stats
    if not _unique_id(db, "call_center_interactions", "interaction_id"):
        result["source_label_consistency"] = {
            "status": "unavailable",
            "reason": "ambiguous_interaction_identity",
        }
        return result
    db.execute("""CREATE TEMP VIEW linked_transcripts AS
        SELECT t.*,i.contact_reason FROM call_transcripts t JOIN call_center_interactions i
        ON t.interaction_id=i.interaction_id AND t.customer_id=i.customer_id""")
    stats = _one(
        db,
        """SELECT count(*) AS matched_rows,
        count(*) FILTER(WHERE main_topics IS NOT NULL AND contact_reason IS NOT NULL)
                AS comparable_topic_rows,
        count(*) FILTER(WHERE main_topics=contact_reason) AS topic_equals_reason_rows,
        count(detected_intents) AS nonnull_detected_intent_rows,
        count(DISTINCT detected_intents) AS distinct_detected_intents
        FROM linked_transcripts""",
    )
    stats.update(
        _one(
            db,
            """SELECT count(*) AS exact_customer_text_groups,
        count(*) FILTER(WHERE reasons>1) AS groups_with_multiple_contact_reasons,
        min(reasons) AS min_reasons_per_group,max(reasons) AS max_reasons_per_group
        FROM (SELECT count(DISTINCT contact_reason) AS reasons FROM linked_transcripts
        WHERE customer_text IS NOT NULL AND contact_reason IS NOT NULL GROUP BY customer_text)""",
        )
    )
    stats["unmatched_or_incoherent_rows"] = (
        result["customer_text"]["accepted_rows"] - stats["matched_rows"]
    )
    result["source_label_consistency"] = {"status": "available", **stats}
    return result


def _surveys(db, tables):
    result = {"scores_by_type": {}}
    for kind in DISTRIBUTIONS["satisfaction_surveys"]["survey_type"]:
        # These constants are reviewed; no user data is interpolated into SQL.
        db.execute(
            "CREATE OR REPLACE TEMP VIEW survey_scores AS SELECT * FROM satisfaction_surveys "
            f"WHERE survey_type='{kind}'"
        )
        result["scores_by_type"][kind] = _distribution(
            db, "survey_scores", "main_score", tuple(str(i) for i in range(11))
        )
    if not _unique_id(db, "call_center_interactions", "interaction_id"):
        result["interaction_coverage"] = {
            "status": "unavailable",
            "reason": "ambiguous_interaction_identity",
        }
        return result
    stats = _one(
        db,
        """SELECT count(*) AS accepted_survey_rows,
        count(*) FILTER(WHERE s.interaction_id IS NULL) AS null_interaction_rows,
        count(*) FILTER(WHERE s.interaction_id IS NOT NULL AND i.interaction_id IS NULL)
                AS unmatched_rows,
        count(*) FILTER(WHERE i.interaction_id IS NOT NULL
            AND s.customer_id IS DISTINCT FROM i.customer_id)
                AS customer_mismatch_rows,
        count(*) FILTER(WHERE s.customer_id=i.customer_id) AS matched_survey_rows,
        count(DISTINCT i.interaction_id) FILTER(WHERE s.customer_id=i.customer_id)
                AS distinct_covered_interactions
        FROM satisfaction_surveys s LEFT JOIN call_center_interactions i USING(interaction_id)""",
    )
    stats["accepted_interaction_rows"] = tables["call_center_interactions"]["accepted_rows"]
    stats["interaction_coverage_rate"] = rate(
        stats["distinct_covered_interactions"], stats["accepted_interaction_rows"]
    )
    stats["additional_surveys_on_covered_interactions"] = (
        stats["matched_survey_rows"] - stats["distinct_covered_interactions"]
    )
    result["interaction_coverage"] = {"status": "available", **stats}
    return result


def _temporal(db):
    result = {"event_process_comparison": {}}
    for table, event in EVENTS.items():
        result["event_process_comparison"][table] = _one(
            db,
            f"""
            SELECT count(*) AS accepted_rows,
                count(*) FILTER(WHERE {event} IS NOT NULL AND process_date IS NOT NULL)
                AS comparable_rows,
                count(*) FILTER(WHERE CAST({event}
                AS DATE)<process_date)
                AS event_before_process_rows,
                count(*) FILTER(WHERE CAST({event}
                AS DATE)=process_date)
                AS event_same_process_day_rows,
                count(*) FILTER(WHERE CAST({event}
                AS DATE)>process_date)
                AS event_after_process_rows,
                min(date_diff('day',CAST({event}
                AS DATE),process_date))
                AS minimum_process_minus_event_days,
                max(date_diff('day',CAST({event}
                AS DATE),process_date))
                AS maximum_process_minus_event_days
            FROM {table}
        """,
        )
    if _unique_id(db, "products", "product_id"):
        result["transactions_before_product_opening"] = {
            "status": "available",
            **_one(
                db,
                """
            SELECT count(*) AS ownership_consistent_rows,
                count(*) FILTER(WHERE t.transaction_date IS NOT NULL AND p.opening_date IS NOT NULL)
                AS comparable_rows,
                count(*) FILTER(WHERE CAST(t.transaction_date
                AS DATE)<p.opening_date)
                AS before_opening_rows
            FROM transactions t JOIN products p
            ON t.product_id=p.product_id AND t.customer_id=p.customer_id
        """,
            ),
        }
    else:
        result["transactions_before_product_opening"] = {
            "status": "unavailable",
            "reason": "ambiguous_product_identity",
        }
    return result


def _risks(tables, transcripts):
    observed = []
    for table, info in tables.items():
        if info["duplicate_excess_rows"]:
            observed.append({"code": "duplicate_effective_keys", "table": table})
        for column, distribution in info["distributions"].items():
            if distribution["suppressed_rows"]:
                observed.append(
                    {"code": "unknown_category_values_suppressed", "table": table, "column": column}
                )
            shape = distribution["class_balance"]
            if shape["distinct_nonnull_values"] == 1:
                observed.append(
                    {"code": "constant_recorded_category", "table": table, "column": column}
                )
            elif (shape["largest_group_share"] or 0) >= 0.9 or (
                shape["largest_to_smallest_ratio"] or 0
            ) >= 20:
                observed.append(
                    {"code": "class_imbalance_heuristic", "table": table, "column": column}
                )
    if transcripts["customer_text"]["duplicate_excess_rows"]:
        observed.append(
            {"code": "repeated_text_random_row_split_risk", "table": "call_transcripts"}
        )
    consistency = transcripts["source_label_consistency"]
    if consistency.get("topic_equals_reason_rows", 0):
        observed.append({"code": "topic_reproduces_source_reason", "table": "call_transcripts"})
    return {
        "observed": observed,
        "leakage_candidates": LEAKAGE_CANDIDATES,
        "interpretation": (
            "Candidates require a decision-time and target contract; "
            "they are not universally prohibited features."
        ),
        "imbalance_heuristic": {
            "largest_group_share_at_least": 0.9,
            "largest_to_smallest_ratio_at_least": 20,
        },
    }


def profile_release(release, data_root="data/processed", *, current_lookup=None):
    """Return a complete aggregate profile or raise a sanitized ProfileError.

    Explicit IDs are offline. `current_lookup` is the read-only publication adapter;
    it returns (curated_release_id, manifest), never rows. No output files are written.
    """
    try:
        directory, manifest, checksum, publication = select_release(
            release, data_root, current_lookup
        )
        with (
            tempfile.TemporaryDirectory(prefix="factored-profile-") as temp,
            duckdb.connect(
                ":memory:",
                config={
                    "threads": 4,
                    "memory_limit": "1GB",
                    "temp_directory": temp,
                    "max_temp_directory_size": "4GB",
                },
            ) as db,
        ):
            db.execute("SET TimeZone='UTC'")
            tables = _register_tables(db, directory, manifest)
            cards = _product_activity(db, tables)
            transcripts = _text_quality(db)
            surveys = _surveys(db, tables)
            temporal = _temporal(db)
        # Check again before exposing results: a changed release must not produce a report.
        _, after_checksum = verify_source(directory)
        if checksum != after_checksum:
            raise ProfileError("source_changed_during_profile")
        reconciliation = {}
        for table in ORDER:
            info = manifest["tables"][table]
            reconciliation[table] = {k: info[k] for k in ("input", "accepted", "rejected")}
            reconciliation[table].update(
                rejection_rate=rate(info["rejected"], info["input"]),
                rejection_reasons=safe_reason_counts(table, info["reasons"]),
                quality_flags=safe_reason_counts(table, info["quality_flags"]),
            )
        return {
            "schema_version": "1.0.0",
            "generated_at": now(),
            "release_provenance": {
                "release_id": manifest["release_id"],
                "raw_release_id": manifest["raw_release_id"],
                "contract_version": manifest["contract_version"],
                "manifest_sha256": checksum,
                "source_kind": manifest["source_kind"],
                "publication_status": publication,
                **safe_provenance(manifest),
                "profiler": fingerprint(),
                "duckdb_version": duckdb.__version__,
                "verification_scope": (
                    "manifest_identity_all_member_sizes_accepted_checksums_and_row_counts"
                ),
            },
            "reconciliation": reconciliation,
            "tables": tables,
            "card_support": cards,
            "transcript_quality": transcripts,
            "surveys": surveys,
            "temporal_quality": temporal,
            "modeling_risks": _risks(tables, transcripts),
            "limitations": [
                "All analytical metrics use accepted Parquet rows; inputs "
                "and rejects come from the release manifest.",
                "Rejection reasons overlap; their counts must not be "
                "summed as distinct rejected rows.",
                "No rejection rows or ML pack contents are scanned; file "
                "integrity is not proof of publication.",
                "Source business cutoff and timezone can be unknown; "
                "event/process offsets are observations, not ingestion delays.",
                "Historical product values do not establish current "
                "banking state or historical as-of eligibility.",
                "Contact reasons and recorded outcomes are not proven "
                "card-specific demand or verified safe resolution.",
                "Survey coverage counts distinct linked interactions, not "
                "invitations or response rate; score types remain separate.",
                "No complaint-product relationship is repaired and no "
                "complaint-transaction relationship is inferred.",
                "Repeated exact texts are not independent examples; source "
                "annotations are not reviewed ground truth.",
                "Only reviewed categorical values are displayed; unknown "
                "strings and source rule names are suppressed.",
                "A zero denominator produces null, not a zero rate. No "
                "currency conversions or monetary totals are computed.",
            ],
        }
    except ProfileError:
        raise
    except (duckdb.Error, OSError, ValueError, TypeError, KeyError):
        raise ProfileError("profile_source_unusable") from None
