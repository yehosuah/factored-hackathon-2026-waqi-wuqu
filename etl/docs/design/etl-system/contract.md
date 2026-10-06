# ETL and backend integration contract v1

Status: approved scope on 2026-10-01; offline integrated implementation verified and
accepted by the user. See [measured acceptance](verification.md). Live S3 activation
is explicitly deferred until runtime credentials are configured.

The two repositories stay independent. Compose joins ETL, backend and PostgreSQL;
each Python repository retains its own lock and test suite. No dataset or credential
is baked into an image. Local volume data is private and excluded from Git.

## Source, grain and types

The accepted full-scope Extract manifest is the sole input membership boundary. Pilot
manifests cannot prepare an authoritative candidate even when they contain all nine tables.
The scope definition and content-derived scope ID must match the full Extract contract.
All nine tables
are prepared. Original bytes and source versions remain untouched. The packaged
`src/factored_bank/etl/contract.json` declares dictionary types, precision, nullability
and keys before transformation. Empty CSV fields alone become null; optional amounts
are never filled, currencies are never converted, and decimals are never rounded to
make an invalid input fit. Source strings and category values are retained.

Dimensions use their entity ID within a source release. Daily tables use entity ID
and process date, preserving history across dates. Repeated effective identities or
dictionary-unique fields are quarantined together, with no arbitrary winner. A future
contract may define a reviewed deduplication rule. Dates of event, process, ingestion
and source modification remain distinct. Source timestamps have unknown timezone;
historical/future synthetic timestamps do not establish a current banking balance.

Every published/rejected row carries source object SHA-256 and one-based CSV logical
record ordinal, process partition and original ingestion time. Invalid required
values, failed type/length/scale checks, partition mismatches and unresolved non-null
references are quarantined. Parent rejection propagates; customer/product ownership
and interaction/customer coherence are checked independently of simple foreign keys.
All inputs reconcile exactly to accepted plus rejected records.
Interaction references additionally match the parent's process date as part of its
effective key, including the independent customer-coherence check.

The user approved two source exceptions after a full profile: registration_branch_id
is unresolved for 149,995/150,000 customers and assigned_branch_id for 831 agents.
Those rows retain their source IDs and explicit quality flags. No fabricated branch
mapping or branch-dependent claim is allowed. Core identity and ownership remain strict.

## Publication and recovery

A complete immutable Parquet directory includes all tables, rejects, checksums, counts,
contract and producing-code provenance. ML sources are optional: when not requested,
`ml.readiness` is `not_included` and no `ml/` directory is required. An explicit ML
source must pass the existing validation or preparation fails; it is never silently
omitted. Included package contents participate in deterministic release identity. It is a prepared candidate
until PostgreSQL publication commits. The loader reconciles every table in one database
transaction before changing the sole accepted-release pointer. Failure preserves the
previous accepted database release. A file pointer is a repairable mirror only;
consumers pin the database release. Repetition verifies and reuses immutable files
and committed database rows. Simulator state is independent of release replacement.

## Consumers

Backend receives its own restricted database role. Test-session authentication and
ownership checks guard all customer APIs. Account/card numbers are masked. Read APIs
label source values historical. Simulator state starts from explicit Active/Closed/
Blocked mappings, treats Suspended as ineligible, and uses labeled team fixtures for
PENDING_ACTIVATION. Pause/reactivation is reversible; a loss/theft block is not. Card
replacement and unrecognized-charge actions register requests only. Actions are
idempotent, audited and verified inside transactions; no refund, fraud adjudication,
payment, issuance or shipping is performed.

ML receives typed organizer exploration tables and, when explicitly included, team-synthetic
Spanish/Portuguese policies, intent, retrieval and handoff datasets. Draft annotations
and approval states are preserved. No scored benchmark, reviewed translation or
independent held-out split is asserted. Organizer conversations remain historical
exploration data rather than a source of authoritative policy or verified tool outcomes.

## Operation and acceptance

ETL runs in its container every 300 seconds without overlap. Source changes/corrections
produce candidates, unchanged input reuses releases, and a successful daily offline
verification records reconciliation progress. Failed runs retain the previous delivery,
persist sanitized diagnostics and retry next cycle. Credentials are runtime secrets.
Offline operation is supported for reproducible tests; it is never called live-source
monitoring. Health tracks accepted data availability and scheduler progress separately.

Acceptance requires both repository checks, meaningful fixture tests, full-data counts,
stable repeat identity, atomic failure recovery, customer isolation, verified simulated
actions and a real Compose startup. These are measured results, not inferred from code.
