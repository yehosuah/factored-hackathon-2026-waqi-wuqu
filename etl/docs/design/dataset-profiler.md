# Feature F: Data Quality / Dataset Profiler v1

The profiler describes immutable curated organizer releases without altering Extract,
Transform, Load, source files, publication pointers or simulator state. It measures
data quality and modeling suitability, not model accuracy or banking success.

## Agreed decisions

Andrew selected 1A and 2A: hybrid publication selection and suppression of unknown
categorical values. `current` must resolve once through PostgreSQL in a read-only
transaction. An explicit curated release ID works offline and reports publication
`not_checked`. A local `current.json` never certifies publication. Source/raw and
curated release IDs are different identities; no raw fallback is allowed.

Display vocabulary is a privacy policy, not a business enum or an intent mapping.
Unknown strings remain in SQL; output contains their row and distinct-value counts.
Source manifest rejection/flag names are similarly filtered. No individual identifiers,
text examples, text hashes, query errors, credentials or full source manifests are emitted.

## Module interface

`factored_bank.profile.profile_release(release, data_root, *, current_lookup=None)`
returns a JSON-compatible aggregate profile or a sanitized `ProfileError`.
`current_lookup` is the publication adapter and returns only `(release_id, manifest)`.
The CLI owns atomic output and terminal formatting. Source selection/validation and
SQL metrics are private implementation. Existing DuckDB, psycopg and filesystem
utilities suffice; no plugin framework or additional dependency is needed.

## Input contract and reconciliation

- Require `card-support-etl-v1`, all nine tables, expected typed Parquet schemas,
  declared effective keys, a valid content-derived manifest identity and complete
  file membership. Reject symlinks within the release and undeclared member names.
- Check sizes of all manifest members and checksums of accepted Parquet files.
  Do not parse reject or ML-pack contents. This is not full ETL verification.
- Check each actual accepted row count against the manifest and
  `input = accepted + rejected`. Reject counts, overlapping rejection reasons and
  quality flags come from the manifest, never reconstructed by summing reasons.
- Recheck accepted checksums and manifest identity before returning results.
  Failures do not publish a partial profile or overwrite a prior successful profile.

## Profile contract

`schema_version = 1.0.0`. Required sections: `generated_at`, `release_provenance`,
`reconciliation`, `tables`, `card_support`, `transcript_quality`, `surveys`,
`temporal_quality`, `modeling_risks`, `limitations`.

All nine tables have row/key/null metrics. Workflow distributions cover products,
transactions, interactions, transcripts, complaints and surveys. Values are exact
source values; booleans use DuckDB's typed `true`/`false` representation.

- Cards are exactly `Tarjeta Crédito` and `Tarjeta Débito`. Show all product types
  (including suppressed counts) before their subset. Card transaction attribution
  requires unique product identity and matching customer ownership.
- `requires_followup` is the existing source field, not `requires_follow_up`.
  Contact distributions are not card-specific support demand.
- Exact-text distinct counts exclude null; duplicate excess is non-null rows minus
  distinct texts. Its denominator and top-five concentration denominator are non-null
  rows. Null counts remain explicit. No text values or hashes leave SQL.
- Survey coverage uses distinct, customer-consistent matched interaction IDs divided
  by all accepted interactions. Multiple surveys cannot inflate coverage. CSAT/NPS/CES
  score distributions remain separate. Displayable scores 0–10 are a privacy vocabulary,
  not a declaration of each survey's valid business range.
- A repeated interaction ID across process dates makes ID-only joins ambiguous:
  skip dependent metrics with a reason rather than inventing an as-of rule or assuming
  equal process dates. The same applies to ambiguous product identity.
- Event/process comparisons count before/same/after and day-offset extrema without
  timezone inference. Product-opening comparisons require ownership-coherent joins.
  No wall-clock-relative analytical metric is used.
- Rates are fractions rounded to eight decimal places; zero denominators are null.
  Imbalance notices use explicit descriptive heuristics: maximum class share >= 0.9
  or largest/smallest class ratio >= 20. These do not establish label validity.
- Leakage candidates are static contract guidance separated from observed checks.
  No monetary aggregation, currency conversion, label creation or relationship repair.

Same data, code and dependency versions produce the same analytical values, regardless
of `generated_at`. Provenance records the producer separately from the profiler.
DuckDB uses four threads, a 1 GB memory budget and at most 4 GB temporary spill under
a private temporary directory removed when the run ends. Only aggregate results enter Python.

## Verification and review

Tests exercise the public interface and CLI using controlled fixture releases, covering
selection, malformed/missing input, schema/checksum/reconciliation failures, deterministic
aggregates, exact card scope, privacy, repetition, ambiguous joins, survey coverage,
temporal anomalies, output safety and exit codes. Run `make check` and `make test`.
Run the real release only if curated Parquet is locally available; do not regenerate
data or quote historical documentation as a new profiler result.

Review the entire uncommitted change against the initial HEAD and the originating
Feature F request, using the repository's existing `docs/agents/gestor-de-issues.md`.
No extra workflow setup, commits or pushes are required.
