"""Profiler behavior through its public interface, using only invented team fixtures."""

import copy
import json

import duckdb
import pytest
from etl_fixtures import raw_release, rows

from factored_bank.etl.common import digest_file, stable_digest
from factored_bank.etl.transform import prepare
from factored_bank.profile import cli, profile_release, source
from factored_bank.profile.source import ProfileError

SECRET = "PRIVATE_TEST_VALUE_941"


@pytest.fixture
def delivery(tmp_path):
    data = rows()
    data["customers"][0]["first_name"] = SECRET
    base = data["products"][0]
    base["opening_date"] = "2023-06-18"
    for number, typ in enumerate(("Tarjeta Débito", "Cuenta Corriente", SECRET), 2):
        data["products"].append(
            {
                **base,
                "product_id": f"products-{number}",
                "product_number": f"TEAM-{number}",
                "product_type": typ,
                "opening_date": "2023-06-17",
            }
        )
    tx = data["transactions"][0]
    tx.update(transaction_status="Approved", transaction_type="Purchase")
    data["transactions"].extend(
        [
            {
                **tx,
                "transaction_id": "tx-2",
                "product_id": "products-2",
                "transaction_status": "Declined",
                "transaction_date": "2023-06-18 10:00:00",
            },
            {**tx, "transaction_id": "tx-3", "product_id": "products-3"},
            {**tx, "transaction_id": "tx-rejected", "amount": "12.345"},
        ]
    )
    interaction = data["call_center_interactions"][0]
    interaction.update(
        contact_reason="Producto",
        reason_category="Producto",
        was_resolved="true",
        was_escalated="false",
        requires_followup="false",
    )
    data["call_center_interactions"].extend(
        [
            {**interaction, "interaction_id": "interaction-2", "contact_reason": "Queja"},
            {**interaction, "interaction_id": "interaction-3"},
        ]
    )
    transcript = data["call_transcripts"][0]
    transcript.update(
        customer_text=SECRET,
        agent_text=SECRET,
        full_text=SECRET,
        main_topics="Producto",
        detected_intents=SECRET,
    )
    data["call_transcripts"].extend(
        [
            {
                **transcript,
                "transcript_id": "transcript-2",
                "interaction_id": "interaction-2",
                "main_topics": "Queja",
            },
            {
                **transcript,
                "transcript_id": "transcript-3",
                "interaction_id": "interaction-3",
                "full_text": SECRET + " suffix",
                "detected_language": "pt",
            },
        ]
    )
    survey = data["satisfaction_surveys"][0]
    survey.update(survey_type="CSAT", main_score="3")
    data["satisfaction_surveys"].extend(
        [
            {**survey, "survey_id": "survey-2", "main_score": "4"},
            {
                **survey,
                "survey_id": "survey-3",
                "interaction_id": "interaction-2",
                "survey_type": "NPS",
                "main_score": "7",
            },
        ]
    )
    manifest, raw = raw_release(tmp_path, data)
    directory, _ = prepare(manifest, raw, tmp_path / "curated")
    return directory


def profile(directory, **kwargs):
    return profile_release(directory.name, directory.parent.parent, **kwargs)


def reseal(directory, change=None):
    """Create a self-consistent fixture identity after deliberately changing source metadata."""
    manifest = json.loads((directory / "manifest.json").read_text())
    for entry in manifest["files"]:
        path = directory / entry["path"]
        if path.is_file():
            entry.update(size=path.stat().st_size, sha256=digest_file(path))
    if change:
        change(manifest)
    identity = {
        k: v for k, v in manifest.items() if k not in ("release_id", "created_at", "provenance")
    }
    manifest["release_id"] = stable_digest(identity)
    (directory / "manifest.json").write_text(json.dumps(manifest))
    target = directory.with_name(manifest["release_id"])
    directory.rename(target)
    return target


def rewrite(directory, table, query):
    path = directory / f"{table}.parquet"
    with duckdb.connect() as db:
        db.read_parquet(str(path)).create_view("original")
        db.sql(query).write_parquet(str(directory / "changed.parquet"))
    (directory / "changed.parquet").replace(path)
    return reseal(directory)


def test_reconciliation_cards_transcripts_temporal_and_surveys(delivery):
    report = profile(delivery)
    rec = report["reconciliation"]["transactions"]
    assert (rec["input"], rec["accepted"], rec["rejected"]) == (4, 3, 1)
    assert rec["rejection_rate"] == 0.25
    assert rec["rejection_reasons"]["counts"] == {"decimal_scale:amount": 1}
    cards = report["card_support"]
    assert cards["accepted_product_rows"] == 4
    assert cards["card_product_rows"] == 2 and cards["card_product_share"] == 0.5
    tx = cards["transaction_activity"]
    assert tx["card_transaction_rows"] == 2
    assert tx["card_transaction_share"] == 0.66666667
    assert tx["recorded_card_declines"] == 1 and tx["recorded_card_decline_rate"] == 0.5
    text = report["transcript_quality"]
    assert text["customer_text"]["distinct_exact_texts"] == 1
    assert text["customer_text"]["duplicate_excess_rows"] == 2
    assert text["full_text"]["distinct_exact_texts"] == 2
    assert text["full_text"]["largest_group_sizes"] == [2, 1]
    assert text["source_label_consistency"]["groups_with_multiple_contact_reasons"] == 1
    assert text["source_label_consistency"]["topic_equals_reason_rows"] == 3
    timing = report["temporal_quality"]
    assert timing["transactions_before_product_opening"]["before_opening_rows"] == 1
    assert timing["event_process_comparison"]["transactions"]["event_after_process_rows"] == 1
    surveys = report["surveys"]
    coverage = surveys["interaction_coverage"]
    assert coverage["matched_survey_rows"] == 3 and coverage["distinct_covered_interactions"] == 2
    assert coverage["interaction_coverage_rate"] == 0.66666667
    assert coverage["additional_surveys_on_covered_interactions"] == 1
    assert surveys["scores_by_type"]["CSAT"]["total_rows"] == 2
    assert surveys["scores_by_type"]["NPS"]["values"][0]["value"] == "7"
    assert surveys["scores_by_type"]["CES"]["class_balance"]["largest_group_share"] is None


def test_deterministic_analytical_values(delivery):
    first, second = profile(delivery), profile(delivery)
    first.pop("generated_at")
    second.pop("generated_at")
    assert first == second


def test_no_sensitive_values_in_output_and_unknown_categories_not_cards(delivery):
    report = profile(delivery)
    encoded = json.dumps(report)
    for private in (SECRET, "products-1", "customers-1", "TEAM-TEST-4242", str(delivery)):
        assert private not in encoded
    distribution = report["tables"]["products"]["distributions"]["product_type"]
    assert distribution["suppressed_rows"] == 1 and distribution["suppressed_distinct_values"] == 1
    assert sum(v["count"] for v in distribution["values"]) + distribution["suppressed_rows"] == 4


def test_offline_id_never_looks_up_database(delivery, monkeypatch):
    def forbidden():
        raise AssertionError("No database connection is allowed")

    monkeypatch.setattr(source, "current_release", forbidden)
    assert profile(delivery)["release_provenance"]["publication_status"] == "not_checked"


def test_current_pins_authoritative_manifest_ignores_file_pointer(delivery):
    root = delivery.parent.parent
    (root / "current.json").write_text(json.dumps({"release_id": "0" * 64}))
    manifest = json.loads((delivery / "manifest.json").read_text())
    calls = []

    def lookup():
        calls.append(1)
        return delivery.name, manifest

    report = profile_release("current", root, current_lookup=lookup)
    assert calls == [1]
    assert report["release_provenance"]["release_id"] == delivery.name
    assert report["release_provenance"]["publication_status"] == "confirmed_at_selection"


@pytest.mark.parametrize("published_manifest", [{}, None, []])
def test_current_manifest_disagreement_fails(delivery, published_manifest):
    with pytest.raises(ProfileError, match="publication_manifest_mismatch"):
        profile_release(
            "current",
            delivery.parent.parent,
            current_lookup=lambda: (delivery.name, published_manifest),
        )


@pytest.mark.parametrize("value", ["../secret", "", "g" * 64, "a" * 63])
def test_invalid_id(value, tmp_path):
    with pytest.raises(ProfileError) as error:
        profile_release(value, tmp_path)
    assert error.value.exit_code == 2


def test_missing_release(tmp_path):
    with pytest.raises(ProfileError) as error:
        profile_release("0" * 64, tmp_path)
    assert error.value.code == "curated_release_missing" and error.value.exit_code == 3


@pytest.mark.parametrize(
    "damage,code",
    [
        (lambda m: m.update(contract_version="next-version"), "unsupported_source_contract"),
        (lambda m: m["tables"]["transactions"].update(input=99), "manifest_reconciliation_failed"),
        (lambda m: m["tables"]["transactions"].update(input=True), "invalid_manifest_count"),
        (lambda m: m["tables"].pop("products"), "incomplete_table_manifest"),
        (lambda m: m["files"].pop(0), "incomplete_release_membership"),
        (lambda m: m["files"].append(copy.deepcopy(m["files"][0])), "invalid_release_membership"),
        (lambda m: m["files"][0].update(path="../secret"), "invalid_release_membership"),
    ],
)
def test_malformed_manifest_contract(delivery, damage, code):
    directory = reseal(delivery, damage)
    with pytest.raises(ProfileError, match=code):
        profile(directory)


def test_actual_accepted_count_must_match_manifest(delivery):
    def change(m):
        m["tables"]["products"].update(input=5, accepted=5)

    directory = reseal(delivery, change)
    with pytest.raises(ProfileError, match="accepted_row_count_mismatch"):
        profile(directory)


def test_tampered_manifest_rejected(delivery):
    p = delivery / "manifest.json"
    m = json.loads(p.read_text())
    m["tables"]["products"]["input"] = 99
    p.write_text(json.dumps(m))
    with pytest.raises(ProfileError, match="manifest_identity_mismatch"):
        profile(delivery)


def test_corrupt_parquet_rejected(delivery):
    p = delivery / "products.parquet"
    b = p.read_bytes()
    p.write_bytes(b"X" + b[1:])
    with pytest.raises(ProfileError, match="accepted_file_checksum_mismatch"):
        profile(delivery)


def test_incompatible_parquet_schema(delivery):
    directory = rewrite(delivery, "products", "SELECT * EXCLUDE(product_status) FROM original")
    with pytest.raises(ProfileError, match="incompatible_parquet_schema"):
        profile(directory)


def test_symlink_member_not_followed(delivery, tmp_path):
    p = delivery / "products.parquet"
    outside = tmp_path / "private.parquet"
    p.rename(outside)
    p.symlink_to(outside)
    with pytest.raises(ProfileError, match="unsafe_member_path"):
        profile(delivery)


def test_rejects_not_parsed_and_unknown_rule_names_suppressed(delivery):
    (delivery / "transactions.rejects.parquet").write_bytes(b"private invalid parquet")
    directory = reseal(
        delivery, lambda m: m["tables"]["transactions"]["reasons"].update({SECRET: 1})
    )
    report = profile(directory)
    counts = report["reconciliation"]["transactions"]["rejection_reasons"]
    assert counts["suppressed_rule_occurrences"] == 1
    assert SECRET not in json.dumps(report)


def test_repeated_interaction_id_across_dates_skips_ambiguous_joins(delivery):
    directory = rewrite(
        delivery,
        "call_center_interactions",
        """
        SELECT * REPLACE ('same-id' AS interaction_id,
            CASE WHEN interaction_id='interaction-2' THEN DATE '2023-06-18'
                 WHEN interaction_id='interaction-3' THEN DATE '2023-06-19'
                 ELSE process_date END AS process_date) FROM original
    """,
    )
    report = profile(directory)
    assert report["tables"]["call_center_interactions"]["duplicate_excess_rows"] == 0
    assert report["transcript_quality"]["source_label_consistency"]["status"] == "unavailable"
    assert report["surveys"]["interaction_coverage"]["reason"] == "ambiguous_interaction_identity"


def test_mismatched_transaction_ownership_not_attributed_to_cards(delivery):
    directory = rewrite(
        delivery, "transactions", "SELECT * REPLACE ('other' AS customer_id) FROM original"
    )
    result = profile(directory)["card_support"]["transaction_activity"]
    assert result["card_transaction_rows"] == 0 and result["ownership_mismatch_rows"] == 3
    assert result["recorded_card_decline_rate"] is None


def test_cli_writes_private_report_and_safe_summary(delivery, tmp_path, capsys):
    output = tmp_path / "profiles"
    assert (
        cli.main(
            [
                "--release",
                delivery.name,
                "--data-root",
                str(delivery.parent.parent),
                "--output-root",
                str(output),
            ]
        )
        == 0
    )
    p = output / delivery.name / "profile.json"
    assert p.stat().st_mode & 0o777 == 0o600
    assert json.loads(p.read_text())["reconciliation"]["transactions"]["accepted"] == 3
    terminal = capsys.readouterr()
    assert "input=" in terminal.out and not terminal.err and SECRET not in terminal.out


@pytest.mark.parametrize(
    "args,code",
    [([], 2), (["--release", SECRET], 2), (["--release", "0" * 64], 3), (["--unknown", SECRET], 2)],
)
def test_cli_failure_codes_and_argument_redaction(args, code, tmp_path, capsys):
    assert cli.main([*args, "--data-root", str(tmp_path)]) == code
    output = capsys.readouterr()
    assert not output.out and SECRET not in output.err
    assert json.loads(output.err)["exit_code"] == code


def test_cli_source_failure_preserves_previous_profile(delivery, tmp_path):
    output = tmp_path / "profiles" / delivery.name
    output.mkdir(parents=True)
    old = output / "profile.json"
    old.write_text("previous")
    (delivery / "manifest.json").write_text(SECRET)
    assert (
        cli.main(
            [
                "--release",
                delivery.name,
                "--data-root",
                str(delivery.parent.parent),
                "--output-root",
                str(output.parent),
            ]
        )
        == 4
    )
    assert old.read_text() == "previous"


def test_cli_cannot_write_inside_source(delivery, capsys):
    assert (
        cli.main(
            [
                "--release",
                delivery.name,
                "--data-root",
                str(delivery.parent.parent),
                "--output-root",
                str(delivery.parent),
            ]
        )
        == 6
    )
    assert json.loads(capsys.readouterr().err)["error_code"] == "output_overlaps_source"
    assert not (delivery / "profile.json").exists()


def test_cli_write_failure_sanitized(delivery, tmp_path, monkeypatch, capsys):
    def fail(*args):
        raise OSError(SECRET)

    monkeypatch.setattr(cli, "atomic_json", fail)
    assert (
        cli.main(
            [
                "--release",
                delivery.name,
                "--data-root",
                str(delivery.parent.parent),
                "--output-root",
                str(tmp_path / "profiles"),
            ]
        )
        == 6
    )
    assert SECRET not in capsys.readouterr().err


def test_current_database_failure_sanitized(tmp_path, monkeypatch, capsys):
    def fail(**kwargs):
        raise source.psycopg.OperationalError(SECRET)

    monkeypatch.setattr(source.psycopg, "connect", fail)
    assert cli.main(["--release", "current", "--data-root", str(tmp_path)]) == 5
    assert SECRET not in capsys.readouterr().err


def test_postgres_selection_is_read_only(monkeypatch):
    calls = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql):
            calls.append(sql)
            return self

        def fetchone(self):
            return ("0" * 64, {})

    monkeypatch.setattr(source.psycopg, "connect", lambda **kwargs: Connection())
    assert source.current_release() == ("0" * 64, {})
    assert calls[0] == "SET TRANSACTION READ ONLY"
    assert len(calls) == 2 and calls[1].startswith("SELECT")


def test_invalid_database_port_is_configuration_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ETL_DB_PORT", SECRET)
    assert cli.main(["--release", "current", "--data-root", str(tmp_path)]) == 5
    result = capsys.readouterr()
    assert SECRET not in result.err
    assert json.loads(result.err)["error_code"] == "publication_configuration_unavailable"
