# Integrated ETL/backend verification

Verified on 2026-10-01 against the complete accepted historical organizer release.
The three Compose services are healthy and the authenticated card-support API is
ready. Runtime mode is **offline**; live S3 discovery has not been verified because
runtime AWS credentials are not configured. The user accepted the verified offline
build on 2026-10-01 and explicitly deferred live S3 activation.
Operation: [runbook](../../etl-operations.md).

## Source and delivery

Raw release: `624156a5cce033722fba62bd27fb2441227ca68395022c58aca1ce9bd3bb6be6`.
Accepted ETL release: `a5ea7a8613c31883cf7c9173f0c541b12c49fd291f0d594432fc798d1c3bf5f4`.
Contract: `card-support-etl-v1`.

| Table | Input | Accepted | Quarantined |
| --- | ---: | ---: | ---: |
| branches | 350 | 350 | 0 |
| customers | 150,000 | 150,000 | 0 |
| products | 400,000 | 399,988 | 12 |
| service_agents | 1,200 | 1,174 | 26 |
| transactions | 4,425,008 | 4,424,802 | 206 |
| call_center_interactions | 686,296 | 670,427 | 15,869 |
| call_transcripts | 171,321 | 143,852 | 27,469 |
| complaints | 67,095 | 22,217 | 44,878 |
| satisfaction_surveys | 212,759 | 207,958 | 4,801 |
| **Total** | **6,114,029** | **6,020,768** | **93,261** |

Reject files preserve original text, source checksum/ordinal and reasons. Reasons may
overlap on a row. Material defects include duplicate product numbers/employee codes,
missing required transcript duration and complaint/product customer mismatches.
The approved branch exceptions remain explicit flags: 149,995 accepted customers
and 811 accepted agents have unresolved branch relationships. No branch mapping is
invented. Rejects and organizer records remain private local files.

ML delivery contains 16 policies, 72 intent cases, 20 retrieval cases and 16 handoff
cases, with ES/PT coverage. These are labeled team-synthetic draft review sources,
exploration-ready; translation/annotation approval and scored evaluation remain out
of scope. Typed organizer tables are delivered separately.

## Measured acceptance

- ETL `make check` passed; pytest executed 207 passing cases. Preexisting duplicate
  test files contribute to that count; seven new transformation tests cover grain,
  types, quarantine, reference propagation, corruption and run locking.
- Backend's own `make check` passed all 22 tests in its independent environment.
- Real PostgreSQL fixture checks passed all-table reconciliation, unchanged reuse,
  corrected release, controlled failure after COPY before commit, rollback of partial
  rows, recovery, and rejection of an incomplete cached database release.
- Real API checks passed authentication, customer isolation for reads/actions, number
  masking, fixture provenance, concurrent idempotency, conflicting keys, eligible and
  ineligible transitions, audited handoff, restricted database permissions, historical
  organizer reads, request-only outcomes, expiry and logout revocation.
- Independent directory consumption verified all table/reject counts, portable
  checksums, ML counts and a private trace back to the original source CSV record.
- Actual backend/ETL restart preserved a temporary team's paused state and verified
  audit; the following ETL run reconciled and reused the same accepted release.
- Fresh isolated PostgreSQL initialization verified runtime-secret import and distinct
  ETL/backend schema owners. Its temporary container was removed after verification.

The final full run started at 19:12:16 UTC and published at 19:16:44 UTC. The restart
repeat started at 19:17:26 UTC and finished at 19:18:37 UTC with `reused: true`.
Detailed aggregate evidence is local in `outputs/etl-system/verification.json`.

## Provenance and boundaries

ETL image: `sha256:f97b7187d7e5630c12ca4e38a59ecf9babed388726ee1d5318d8d3977a62541e`.
Backend image: `sha256:d8bb788117a225d30db286fc4ba21a7de0644d2f15e9e3b003677e8a4c6cd931`.
Producing source-tree digest:
`6da4b45a061a02de7aa9243aded92b8adad45fc3c86de732cbfa855c07eeca78`.
Dependency-lock digest:
`37f78cdd94fe50e8de080bd418a926c05eb6b20b1acfc2113930e716f27d56cd`.
Container Git revision is unavailable; code and lock content digests identify the
executed files. Both repositories were verified on separate working branches before
their implementation commits; the recorded digests identify the built runtime code.

This evidence covers the local historical hackathon prototype. It does not establish
current banking balances, live S3 monitoring, reviewed ML quality or production-bank
deployment readiness. The scheduler is active every five minutes in offline mode;
switching to live mode requires private AWS credentials and a successful source run.
