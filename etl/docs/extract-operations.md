# Extract v1 operator guide

Extract preserves the original CSV bytes from the nine agreed organizer tables and publishes
a complete, structurally verified raw release. It does not filter cards, join entities, repair
values, deduplicate business rows or load backend tables. Execution is manual; no scheduler
is configured. The controlling design is the [accepted contract](design/extract-card-support/extract-v1-contract.md).

## Setup and credentials

From the ETL repository root:

```bash
uv sync --locked
make check
make test
```

The connector uses boto3's standard AWS credential provider chain. Configure a dedicated local
AWS profile or process environment outside versioned files. `AWS_PROFILE`, `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY` and, where necessary, `AWS_SESSION_TOKEN` are supported by that chain.
The pipeline does not automatically load `.env` files. Never pass secrets as command arguments
or insert them into manifests, fixtures, documentation or Git. AWS CLI and PowerShell are not
required to run this pipeline.

Default source: the agreed organizer bucket, prefix `data/`, region `us-east-2`.
The source connector lists and reads objects only. Four root tables (`customers`, `products`,
`branches`, `service_agents`) and five daily tables (`transactions`, `call_center_interactions`,
`call_transcripts`, `complaints`, `satisfaction_surveys`) are selected. Other tables and the
backup prefix are outside this scope.

## Manual workflow

```bash
# Inventory and estimates only; no full-object download or publication.
uv run --locked factored-extract plan --scope pilot --pilot-date 2023-06-17

# Four complete root CSVs and one object from each daily table.
uv run --locked factored-extract run --scope pilot --pilot-date 2023-06-17
uv run --locked factored-extract verify --scope pilot --pilot-date 2023-06-17

# Inspect the full historical inventory, then acquire it.
uv run --locked factored-extract plan --scope full
uv run --locked factored-extract run --scope full
uv run --locked factored-extract verify --scope full

# The same command performs incremental reconciliation and verified reuse.
uv run --locked factored-extract run --scope full
```

Operational invocations return JSON, including invalid arguments; `--help` prints usage. Retain the accepted release ID and manifest reference from a
successful run. `plan` is not an accepted release. A successful repeat reports `unchanged` with
the same release ID and a new run ID; reused objects are rehashed and structurally rechecked.
New partitions are detected by inventory, even when their partition date is older than the
latest observed date. Corrections retain prior bytes and produce a new accepted release.

Optional storage roots are `--raw-root` and `--output-root`. Defaults are `data/raw/organizer`
and `outputs/extract`. The roots must be separate, non-nested directories on the same filesystem.
Use supported local filesystem storage; do not assume network or
cloud-synced folders have the same locking and durability guarantees. The current implementation
targets the local macOS/POSIX environment.
Publication uses POSIX `flock`, `fsync` and atomic filesystem replacement. Windows and
non-local filesystems require separate validation; the current tests do not establish their
locking or crash-durability behavior.

Use `run --plan <plan-path>` to execute a previously saved plan; the source inventory and
validation configuration are checked again, so a stale plan cannot silently expand or shrink.
Use `verify --release-id <release-id>` for a historical release, retaining its original
`--scope` and `--pilot-date` where applicable. Verification does not create an AWS client or
resolve credentials. `--workers` defaults to four; `--field-limit` defaults to 16 MiB.
The field limit is measured in UTF-8 bytes, including for multibyte characters.
Run `uv run --locked factored-extract --help` for the complete interface.

## Outputs and their meaning

| Output | What it provides |
| --- | --- |
| `data/raw/organizer/objects/` | Immutable original byte sequences addressed by local SHA-256 |
| `data/raw/organizer/staging/<run-id>/` | In-progress or failed acquisition evidence; never a consumption interface |
| `data/raw/organizer/current/<scope-id>.json` | Atomic pointer to a release manifest and its digest |
| `outputs/extract/runs/<run-id>/plan.json` | Selected source identities, coverage and acquisition plan |
| `outputs/extract/runs/<run-id>/result.json` | Status, counts, timings and accepted/candidate release references |
| `outputs/extract/runs/<run-id>/diagnostics.json` | Sanitized failure/update evidence without individual records |
| `outputs/extract/releases/<release-id>/manifest.json` | Complete accepted scope, source identities, hashes, structural counts and provenance |
| `outputs/extract/releases/<release-id>/manifest.sha256` | Integrity check for the complete immutable manifest, including historical releases |

Pilot and full scope have different pointers. Downloaded bytes can be reused across them, but
a pilot can never stand in for a full-history release. Read a validated manifest, not an arbitrary
CSV directory or the latest download delta. An old release remains identifiable after a correction;
its usability still depends on its referenced local files passing verification.

For Run, `downloaded + reused + failed + not_attempted` must equal the planned object count. Publication
requires no failed or unattempted objects and no unresolved source/schema discrepancy. Logical
CSV row counts exclude headers; quoted embedded newlines are part of one field. Valid header-only
files have zero rows. The counts do not certify upstream completeness or business correctness.

Date gaps are coverage findings. Unknown source cutoff/timezone and the dictionary's snapshot
discrepancy remain explicit limitations. LastModified and recheck times do not establish the date
through which bank activity is complete. Local SHA-256 verifies local content; remote checksum
status states separately whether a comparable source checksum could be validated.

## Status and exit codes

| Status | Meaning |
| --- | --- |
| `planned` | Inventory plan persisted; no release published |
| `published` | Complete accepted release made current |
| `unchanged` | Accepted logical release retained after successful revalidation |
| `verified` | Requested local release passed offline verification; no source access or new publication |
| `review_required` | Source/schema discrepancy requires review before acceptance |
| `failed` | Requested acquisition/validation/storage action failed |
| `unavailable` | No usable release can be asserted for the request |

Exit codes are `0` success, `2` invalid configuration/contract, `3` review required,
`4` acquisition/validation/storage failure and `5` lock contention. JSON `error_code` provides
the specific reason. A previous release reference in a failed result does not certify that its
files remain usable; run offline verification before relying on them.

`verified` is the implementation's explicit success status for the contract's Verify action;
it distinguishes a local integrity check from publishing or rechecking the source inventory.

## Failure and recovery

- If selected source objects change while a run is executing, the candidate is held. Start a
  new manual run to build a fresh inventory; verified downloads may be reused.
- If a previously accepted source key disappears, investigate with the source owner. Do not
  delete local history or silently remove the key to bypass review.
- If a header changes, preserve the evidence and review a versioned contract change. Do not
  auto-learn new headers or modify received CSV bytes to make validation pass.
- If a local object is damaged, `verify` reports failure. `run` attempts reacquisition against
  the planned source identity. If reconstruction fails, the release is unavailable.
- If another run holds the local lock, wait for it to finish. Do not delete the lock file while
  a process is active. The operating-system lock governs ownership.
- After a crash, rerun the action. Recovery reconciles a committed current pointer with its
  manifest. No automatic recursive cleanup or history deletion is performed.
- For insufficient disk or permissions, correct the local condition and retry. Preflight space
  checks cannot prevent another process from exhausting storage later.

The source adapter retries transient transport failures at most three total attempts per
operation. Access denial, incompatible CSV and changed source identities are not transient.
Partial streams cannot be published. Diagnostics are sanitized; use stable error codes without
printing source rows or credential-bearing exception text.

Run results record the checking code fingerprint, contract versions and sanitized configuration
digest for each execution, including unchanged runs. The immutable manifest retains the original
producing-code evidence. Per-object run diagnostics record transfer attempts and received payload
bytes; reuse has zero acquisition attempts and zero transferred bytes.

## Verification and remaining boundaries

The behavior suite uses controlled team fixtures to exercise new arrivals, corrections,
deletions, schema drift, source changes, partial transfer and local corruption without changing
the organizer bucket. Source-adapter and storage tests cover their specific protocol boundaries.
These results are distinct from the measured real-source pilot, full-history acquisition and
repeat evidence in local run manifests. See the [verification report](design/extract-card-support/verification-v1.md)
for acceptance results and exact local evidence references.

Five-minute detection and daily inventory reconciliation are future design cadences, not active
schedules or guaranteed end-to-end freshness. Live source integration must revisit the publication
boundary for a continuously changing source. Transform requires explicit user approval after
Extract review; Load requires an agreed destination and strategy. Card policies, operational
agent availability and branch capabilities remain separate future team sources.
