# Extract v1: decision and implementation contract

Date: 2026-09-27. Status: design accepted; implementation subsequently authorized and completed. See the [verification report](verification-v1.md) for measured acceptance evidence.

This addendum records the accepted Extract v1 design. The user first approved the complete contract and paused before implementation, then explicitly authorized implementing the pipeline without scheduling. Earlier policy decisions and the engineering defaults accepted in the final review are distinguished below. The original guide and Word export remain the historical v1.0 design; this addendum is the accepted follow-up baseline.

## 1. Outcome and phase boundary

An operator can acquire the nine agreed organizer tables, preserve their original bytes and versions, and identify one complete, structurally accepted raw release with reproducible evidence. A repeat or failed attempt must not silently duplicate content, discard history, or expose a partial release.

The design review is complete and implementation is authorized. Entering Transform still requires a functional, verified Extract and a separate explicit transition decision. Load is also outside this phase.

## 2. Decisions already settled

| Decision | Basis |
| --- | --- |
| Nine tables: customers, products, branches, service_agents, transactions, call_center_interactions, call_transcripts, complaints, satisfaction_surveys | Explicit user selection |
| All available history; representative pilot first | Explicit user selection |
| Original CSV bytes and previous versions remain local under data/raw/; manifests under outputs/; neither in Git | Explicit user selection |
| Manual initial and incremental runs; no active scheduler | Explicit user selection |
| Future change detection every five minutes and daily full reconciliation | Explicit user selection; target cadence, not an end-to-end freshness SLA |
| Team-created card policies and business fixtures are separate sources whose contents need agreement | Explicit user selection; not created by the first historical extraction |
| Completeness is reconciliation against the observed inventory; date gaps and valid zero-row files are reported | Explicit user selection in the latest design round |
| A previously accepted object disappearing from the source holds the next release for review; local history is retained | Explicit user selection in the latest design round |
| Unexpected header changes hold the candidate release, including additional, removed, renamed, reordered or duplicate columns | Engineering selection under the user's delegation to choose the safer schema policy |

Schema review is a visible contract revision, not an automatic acceptance of whatever arrived. Files can be acquired and retained as evidence without being eligible for an accepted release. Nulls, duplicate business rows and original values are not repaired or filtered by Extract.

## 3. Source scope and evidence limits

- Source: `s3://factored-datathon-2026-s3-157725502942-us-east-2-an/data/`, region `us-east-2`, read-only.
- Four exact root keys: `customers.csv`, `products.csv`, `branches.csv`, `service_agents.csv`.
- Five daily table prefixes: transactions, call_center_interactions, call_transcripts, complaints and satisfaction_surveys. Observed paths follow `table/year=YYYY/month=MM/day=DD/table_YYYYMMDD.csv` under `data/`.
- A selected table's unexpected object layout is reported and holds publication for contract review; it must not disappear through a silent filename filter. Folder markers are metadata, not CSV inputs. Out-of-scope table prefixes and `data_backup_20260831/` are not acquired.
- Observed baseline: 5,489 selected CSV objects, 1,265,179,481 bytes. Five daily tables each had 1,097 objects with first/last listed dates 2023-06-17 and 2026-06-17. These are observations, not hard-coded future counts or evidence of row-level quality.
- At design acceptance, only one header per selected table had been inspected. The implementation verification report records subsequent all-file schema, CSV, count and coverage measurements; the design observations alone did not establish those facts.
- No upstream completeness manifest was established. All nine table locations must be present. Missing calendar dates are coverage findings, not fabricated empty files or proof of upstream completeness.
- Header-only CSVs can pass structural checks with zero logical records. Zero-byte files, missing headers and entirely absent selected tables cannot pass.
- customers, products and service_agents are delivered as single files despite the dictionary's monthly-snapshot description. Extract preserves this discrepancy. It does not infer historical snapshots, business cutoff or source timezone.

## 4. Source consistency design — TBD-03

For the historical source, use a deliberately conservative acquisition protocol:

1. Acquire the local run lock and finish recovery checks before inspecting the current release.
2. List every page of the selected scope and persist an immutable acquisition plan. Record listing start/end and each object's key, size, ETag and LastModified.
3. Compare the inventory with the last accepted release for the same scope. A missing previously accepted key is a review-required discrepancy.
4. For new/changed objects, inspect metadata and stream bytes using the planned ETag as an If-Match condition. Record VersionId when returned; do not require version-specific permissions for this first connector.
5. Verify returned metadata and received length against the planned object identity. A precondition failure, disappearance or conflicting identity is not a transient network error and does not silently replace the plan.
6. Before publication, repeat the complete selected-scope listing. If selected keys or their identity metadata differ from the plan, hold the candidate release. A new manual run builds a new plan and may reuse individually verified downloads.

For this static-source v1, even an arrival during the run waits for a new plan. This favors an explainable delivery over continuously changing the scope of a running extraction. It may not be suitable for a continuously mutating source; live integration must revisit the batch boundary before enabling five-minute execution.

Two matching listings and conditional reads provide acquisition evidence, not a transactional snapshot across nine tables. S3's per-object consistency does not supply a multi-object transaction. See [S3 consistency](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html#ConsistencyModel) and [GetObject conditional reads](https://docs.aws.amazon.com/AmazonS3/latest/API/API_GetObject.html).

## 5. CSV contract design — TBD-04 and TBD-05

The pilot must verify this explicit supported dialect; incompatible inputs stop acceptance rather than trigger silent format guessing:

| Concern | v1 rule |
| --- | --- |
| Encoding | Strict UTF-8; an initial UTF-8 BOM is accepted and recorded for parsing; original bytes remain untouched |
| Delimiter and quoting | Comma delimiter, double-quote quoting, doubled quote escaping; no implicit backslash unescaping |
| Record endings | LF or CRLF; quoted newlines belong to a field, not a new record |
| Header | One header record; exact ordered names from the reviewed table contract; no trimming, renaming or duplicate/empty names |
| Rows | Every logical record must have the header's field count; a completely blank record outside quoted text is a structural error, not silently dropped |
| Empty values | Preserve empty fields and literal null markers; no null conversion or required-field business checks here |
| Counts | Count successfully parsed logical data records, excluding the header; a malformed file does not receive a misleading complete row count |
| Malformed input | Preserve bytes and sanitized failure evidence; hold publication; never repair a record in place |
| Resource limit | Explicit configurable field-size limit, initially 16 MiB; exceeding it is a named failure, never truncation |
| Types | Preserve text representation; do not coerce dates, identifiers, decimals, currencies or booleans |

The nine expected header lists must be recorded in the versioned input contract before runtime code accepts them. Use the inspected headers and dictionary as review evidence, not runtime auto-learning. Every selected file is checked against that contract during extraction. Any pilot mismatch returns to contract review before the full acquisition proceeds.

## 6. Storage and release design — TBD-07

Use immutable, content-addressed raw storage: the local SHA-256 names the stored byte sequence; a manifest maps each source key and observed identity to that content. Equal content may share one stored file while retaining separate source entries.

```text
data/raw/organizer/
  objects/<sha256-prefix>/<sha256>.csv
  staging/<run-id>/...part
  current/<scope-id>.json
  .extract.lock
outputs/extract/
  runs/<run-id>/plan.json
  runs/<run-id>/result.json
  runs/<run-id>/diagnostics.json
  releases/<release-id>/manifest.json
```

These paths are implemented. Immutable release directories also contain `manifest.sha256`; a recoverable acquisition index lives under the raw root. Manifest content paths are relative to declared storage roots; operator result paths are absolute local conveniences. Source keys are metadata; they are never blindly joined into filesystem paths. Reject symlink/path escapes outside managed roots.

There are separate scope identities and current pointers for the pilot and the full history. A successful nine-object pilot can never become the full-history current release. Their verified content can be reused.

An accepted release enumerates every object in its scope, including unchanged reused objects. A raw folder is not the consumption interface. Downstream work opens an explicit release manifest and checks its acceptance status and scope.

Compute release identity deterministically from canonical scope, contract/validation version and complete object entries, including source identities, local hashes and structural results. Exclude run timestamps and downloaded-versus-reused dispositions. An unchanged validated run keeps the same release ID and writes a new run result. A changed source identity is recorded even when the received bytes are identical.

Original ingestion time and source cutoff do not become newer merely because an object was rechecked. Record `checked_at` separately; unknown source business cutoff stays unknown.

## 7. Publication, recovery and local integrity design — TBD-08

- One operating-system lock per managed raw root covers a whole run. A competing process reports `run_locked`; it cannot publish concurrently. The initial implementation targets the local macOS environment; other hosts require validation of locking and durability behavior.
- Reused content is rehashed and structurally revalidated under the current contract before acceptance. At the current approximately 1.27 GB scope, correctness is preferred over an unmeasured cache optimization.
- If cached content is missing or corrupted, reacquire the planned source object. If the source no longer permits reconstruction, report unavailable; do not claim that a damaged previous release remains usable.
- Stage each download in a unique run location. Finalize immutable objects before making the release visible. Files from a failed run may be reused only after identity and content checks.
- Write and flush the immutable release manifest and its referenced objects before atomically replacing the small current pointer. Flush the relevant directories. Require supported local filesystem semantics for these roots; network/cloud-synced filesystem behavior is not assumed.
- The current pointer plus validated manifest is the publication truth. If a crash happens after pointer replacement but before the run report finishes, recovery reconciles that fact rather than publishing twice or reporting a false rollback.
- Do not modify manifests of already accepted releases. A correction creates another release. A run with no prior release and a failure reports unavailable, not an empty successful dataset.
- Check free space before transfer against outstanding bytes plus a staging/metadata margin, and handle mid-run disk exhaustion. A check is not a guarantee against other processes filling the disk.
- No automatic deletion of raw history or failed-run evidence in v1. Partial files cannot be consumed. Cleanup/retention changes require a separate, reviewed action; no recursive directory cleanup is part of recovery.

## 8. Transport and runtime design — TBD-09 to TBD-11

Use Python 3.13 and boto3 in the ETL's uv-locked environment. The first connector needs S3 listing, metadata reads and object GETs only. Do not install PowerShell or depend on a shell `sync` command to define release correctness. No S3 writes or changes to the organizer's bucket are made.

Initial tunable defaults, to measure during the pilot:

| Control | Accepted initial setting |
| --- | --- |
| Concurrent object downloads | 4 |
| Connect timeout | 10 seconds |
| Read timeout | 60 seconds without progress; not a whole-file duration promise |
| Retry budget | At most 3 total attempts per transport operation, including the first; one retry owner so SDK and application retries do not multiply |
| Backoff | Exponential with jitter, capped at 20 seconds between attempts |
| Retryable cases | Transient connection/stream failures, throttling and applicable server failures |
| Non-retryable cases | Access denied, invalid configuration, schema/CSV errors, source identity conflict or disappearance |
| Download recovery | Retry the whole object; no byte-range resume in v1 |
| Transfer memory | Stream in bounded chunks rather than loading whole objects into memory; measure peak memory in the pilot |

Stop new work on a terminal run error; account for pending/cancelled objects explicitly. There is no automatic endless whole-run restart. All retries use the same planned identity; a new source version requires a new plan.

Use the standard SDK credential provider chain, with a dedicated local AWS profile or process environment. Credentials do not appear in contract files, command arguments, manifests, screenshots in documentation, fixtures or logs. Do not persist the credential image or OCR logic as part of the extractor. New managed private directories/files use restrictive local permissions (0700/0600 where supported). See [Boto3 credential configuration](https://docs.aws.amazon.com/boto3/latest/guide/credentials.html).

Compute local SHA-256 for every finalized byte sequence. Request and record available S3 checksum metadata where supported; explicitly state whether a remote checksum was validated, unavailable or unsupported. Supported validation failures hold publication. Never treat ETag or a multipart composite checksum as a universal whole-file SHA-256/MD5. Absence of a comparable remote checksum is recorded, not disguised as independent verification. See [S3 integrity documentation](https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity-upload.html).

## 9. Operator and consumer interface design

Expose one small Extract interface with three operator actions. Exact command spelling is an implementation detail:

| Action | Observable result |
| --- | --- |
| Plan | Read and persist the approved inventory, estimated download/reuse bytes, coverage findings and blockers; download no complete objects and publish nothing |
| Run | Execute an initial or incremental plan, account for every object, return the run result and accepted release identity when successful |
| Verify release | Verify manifest, referenced files, hashes, structural evidence and scope without contacting S3; report valid or unavailable |

`Run` revalidates a supplied plan's source identities; an old plan is never blindly trusted. Reconciliation is the full-scope comparison behavior of the same module, not a second independent pipeline. No scheduler is configured.

Agreed machine-readable result fields: `result_schema_version`, `run_id`, `status`, `scope_id`, `candidate_release_id`, `accepted_release_id`, `previous_release_id`, `downloaded`, `reused`, `failed`, `not_attempted`, `warnings`, `error_code`, and references to the plan/manifest. Raw row payloads never appear in a result.

Statuses distinguish `planned`, `published`, `unchanged`, `review_required`, `failed` and `unavailable`. A plan result is not an accepted extraction. Exit zero indicates success for the requested action; nonzero indicates an error or review requirement. A verification failure must never return a successful release result.

Agreed exit classes: 0 success, 2 invalid configuration/contract, 3 review required (source/schema change), 4 acquisition/validation/storage failure, 5 lock contention. Include a more specific stable error code in JSON. These actions are now exposed by `factored-extract`; see the operator guide for command syntax and the explicit `verified` success status.

## 10. Manifest and reconciliation contract

| Group | Required evidence |
| --- | --- |
| Identity | Manifest schema, release ID, scope ID/digest, input contract and validation version |
| Reproducibility | Producing run, code revision when available, dirty state and source-tree digest, dependency-lock digest, sanitized configuration digest |
| Source | Logical source ID, bucket/region/prefix, listing windows, both inventory comparisons |
| Per object | Table, source key, size, ETag, LastModified, VersionId when returned, original partition path, observed remote checksum information |
| Local content | Safe relative reference, SHA-256, received bytes, original acquisition time, checked time, encoding/dialect/header evidence and logical row count |
| Coverage | Included tables and dates, missing calendar dates, zero-row files, snapshot/cutoff limitations; no invented source row totals |
| Publication | Complete inventory, validation result, publication status and release-manifest digest in the current pointer |

Run-specific reports hold attempts, transfer/reuse dispositions, failures and the previous release reference. Keep these outside the immutable content identity so repeat checks do not pretend to produce new data.

Reconciliation invariants:

1. Every planned object has one terminal disposition: downloaded-and-verified, reused-and-verified, failed, or not-attempted/cancelled.
2. Publication requires zero failed and zero not-attempted objects, all nine required table locations, and no unresolved schema/source discrepancy.
3. Expected object count equals the sum of all terminal dispositions. Verified byte totals reconcile with the planned objects, independently of bytes transmitted over the network.
4. Release row counts describe the logical records in the accepted CSVs. No deduplication, business filtering or source-certified row reconciliation is implied.
5. An accepted full-history manifest includes unchanged objects, not merely the latest download delta.
6. A historical release remains identifiable after corrections. It is usable only if its referenced content verifies.

## 11. Verification seam and acceptance matrix

Agreed primary test seam: invoke the same Extract coordinator used by the operator, with a controlled source adapter and a temporary raw repository. The real S3 adapter and controlled source justify a small source interface. Test SDK request construction separately for pagination and conditional reads. Do not introduce a generic multi-cloud framework.

| Scenario | Required evidence |
| --- | --- |
| Pilot | Four complete root CSVs plus one daily object per selected daily table; about 116.15 MB at the observed sizes; pilot scope cannot publish as full history |
| Full acquisition | All objects from a freshly approved inventory received or reused, structurally checked, and included in the accepted release |
| Identical second run | Same logical release ID; a new run report; no repeated content storage; reuse verification actually performed |
| Late/new partition | Old partition date does not prevent acquisition; unchanged objects remain in the full release |
| Correction | New source identity retained alongside old bytes; corrected release references the right content |
| Source changes during run | Conditional conflict or changed final listing holds publication; a new plan can reuse valid content |
| Source disappears | Review-required result; no deletion of local history or automatic dropping from active scope |
| Header/schema change | Raw evidence preserved; no auto-learned replacement contract; previous accepted pointer unchanged |
| CSV cases | UTF-8/BOM, quoted commas/newlines, escaped quotes, zero rows, blank records, bad encoding, inconsistent row shape and field-size limit tested |
| Network interruption | Partial bytes never accepted; bounded same-identity retry; no mixture of versions |
| Local corruption | Detected before reuse; repaired from source or reported unavailable |
| Publication crash | Faults before/after the commit point recover to an explainable accepted pointer and run outcome |
| Concurrent invocation | Second publisher refused; no racing current pointers |
| Disk/access failures | Bounded, sanitized failure; no false successful or empty release |
| Coverage gaps | Reported separately from inventory reconciliation; not converted to invented files |
| Secrets and privacy | No credential or individual-record leakage through tracked files, diagnostic output or fixtures |

Real-source evidence requires the pilot, full historical acquisition and repeat run. Controlled fixtures establish failure/update behavior without modifying the organizer bucket. Record actual duration, transferred bytes, reused bytes and peak memory; no throughput promise is made before measurement.

After implementation, run the ETL's `make check` and relevant behavioral tests. The original design document did not establish test results; the linked verification report records implementation evidence.

## 12. What still requires a later decision

| Item | Why it does not block historical Extract | Required gate |
| --- | --- | --- |
| Exact business cutoff, timezone and snapshot content | Original bytes and uncertainty can be preserved faithfully | Before temporal transformations or customer-facing freshness claims |
| Card policies, agent availability, branch replacement capability | They are distinct team sources, not hidden fields to invent in organizer CSVs | Before simulating those business decisions |
| Actual live source and complete-publication signal | Current source is static; fixtures can test updates | Before live integration and scheduled execution |
| Transform keys, joins, null treatment, decimal types and card filtering | These change meaning/content rather than acquire originals | Explicit Transform phase approval |
| Model labels, safe splits and Portuguese evidence | Preserving raw provenance does not require selecting an ML method | Before preparing AI/evaluation datasets |
| Load destination and strategy | Local raw is the agreed Extract destination only | Explicit Load design and destination agreement |
| Production retention, deployment and operational ownership | v1 is local, manual and preserves history without automated disposal | Before production deployment |

## 13. Closure and next gate

TBD-02, TBD-05 and TBD-06 have the policy decisions recorded in section 2. The user also accepted sections 4–11 as the design baseline for TBD-03, TBD-04 and TBD-07 through TBD-11. Those design decisions are closed; source conformance and pilot performance still require actual implementation evidence. Adjustable pilot settings are initial choices, not measured facts about the source.

Original design-review outcome: the user selected “Accept the Extract design; stop before implementation for now.” In a subsequent instruction, the user authorized Extract pipeline implementation without scheduling. The implementation must demonstrate pilot, full-history and repeat-run evidence; moving to Transform still requires a separate explicit approval after Extract is functional. Load remains outside this phase.
