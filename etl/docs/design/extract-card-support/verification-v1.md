# Extract v1 verification evidence

Date: 2026-09-27, America/Guatemala. Machine timestamps are UTC and cross into 2026-09-28.
Status: manual Extract v1 implemented and verified. Software checks, organizer pilot, full
acquisition, identical repeat and full offline verification passed. No scheduler, Transform
or Load implementation is included.

The [accepted contract](extract-v1-contract.md) controls scope. The
[operator guide](../../extract-operations.md) explains commands and recovery.
The earlier Word design remains a historical design artifact.

## Software evidence

The complete automated suite passed: **100 tests in 2.55 seconds**, plus **`make check`**. The latter checks the
dependency lock, lint, formatting and the small environment demonstration. These checks are
separate from the organizer dataset and do not certify its row-level business quality.

Controlled team fixtures establish these behaviors:

- Planning without full-object downloads; separate pilot and full scope identities.
- Complete initial publication, unchanged repeat identity and verified local reuse.
- Late partitions and corrections with previous releases and original ingestion times retained.
- Source disappearance, schema drift and changes during acquisition holding publication.
- CSV dialect/header enforcement, zero-row files, coverage findings and bounded field sizes.
- Conditional S3 reads, pagination, bounded transport retries and incomplete-stream rejection.
- Corruption detection and repair/unavailability, lock contention and crash commit boundaries.
- Safe paths, sanitized evidence, complete terminal object accounting and private storage.
- Missing acquisition-index recovery from accepted manifests without redownloading valid bytes.
- Result persistence while holding the operating-system lock.
- Offline named-history verification independent of an unrelated broken current pointer.
- Separate checking-code provenance and contract versions for each execution, including an
  unchanged release; the immutable manifest retains its original producing-code provenance.
- Invalid CLI arguments return sanitized JSON and exit 2 without echoing supplied values.
- The CSV field-size limit counts UTF-8 bytes, including multibyte text, rather than treating
  a character count as equivalent to a byte limit.

The simulated source updates and failures do not modify the organizer bucket. No tests exercise
Transform, Load, live banking operations or scheduling because those are outside this phase.

## Organizer pilot: passed

The pilot includes the four complete root CSVs and the 2023-06-17 object from each of the five
daily tables. It is an accepted **pilot** release, not the full historical scope.

| Measure | Observed result |
| --- | --- |
| Acquisition status | `published`, exit 0 |
| Objects planned / downloaded / reused | 9 / 9 / 0 |
| Failed / not attempted | 0 / 0 |
| Bytes planned, received and verified | 116,150,824 |
| Logical CSV data records | 555,065 |
| Acquisition duration | 137.539 seconds |
| Acquisition peak process memory | 80,134,144 bytes |
| Offline verification status | `verified`, exit 0 |
| Offline verification duration | 2.990 seconds |
| Offline bytes verified / transferred | 116,150,824 / 0 |
| Offline verification peak process memory | 44,023,808 bytes |

The acquisition count reconciles: 9 planned = 9 downloaded + 0 reused + 0 failed + 0 not attempted.
Offline verification read all nine local objects and checked hashes and structural evidence
without contacting S3. Durations are actual observations, not future throughput guarantees;
peak memory is the operating system's process high-water mark, not per-object memory.

| Table | Pilot logical records |
| --- | ---: |
| customers | 150,000 |
| products | 400,000 |
| branches | 350 |
| service_agents | 1,200 |
| transactions | 2,886 |
| call_center_interactions | 384 |
| call_transcripts | 88 |
| complaints | 38 |
| satisfaction_surveys | 119 |

All nine files have local SHA-256 evidence. Seven objects also passed comparison with an S3
whole-object CRC32 checksum. `customers` and `products` expose multipart **composite** CRC32
checksums; this implementation records those as unsupported for whole-file comparison. Their
remote checksum metadata is preserved, but the report does not claim independent whole-object
remote checksum validation for them. Their planned identity, received length, local SHA-256 and
CSV structure were verified.

Local evidence:

- Acquisition run: `6b8887ffc02f4e508222543b1916b131` —
  [result](../../../outputs/extract/runs/6b8887ffc02f4e508222543b1916b131/result.json).
- Accepted pilot release: `e8f106f340e5b752ae061db4f8575c99dc368b65071897da0604168f929bd919` —
  [manifest](../../../outputs/extract/releases/e8f106f340e5b752ae061db4f8575c99dc368b65071897da0604168f929bd919/manifest.json).
- Offline verification run: `7aa402c01c1042e8a04bfa2432c330b0` —
  [result](../../../outputs/extract/runs/7aa402c01c1042e8a04bfa2432c330b0/result.json).

These links refer to private local evidence, ignored by Git. No raw rows or credentials are
included in this report. The manifest records a source-tree digest and dependency-lock digest;
the Git revision was unavailable and the working tree was dirty. Reproducibility therefore
relies on those recorded fingerprints rather than an invented commit identifier.

## Full history: acquired, repeated and verified offline

The full acquisition published an accepted release containing **5,489 selected CSV objects,
1,265,179,481 bytes and 6,114,029 logical CSV records**. Initial and final selected inventories
matched. Every planned object was downloaded or reused and structurally verified.

| Measure | Observed result |
| --- | --- |
| Acquisition status | `published`, exit 0 |
| Objects planned / downloaded / reused | 5,489 / 5,480 / 9 |
| Failed / not attempted | 0 / 0 |
| Total verified bytes | 1,265,179,481 |
| Newly transferred bytes | 1,149,028,657 |
| Verified bytes reused from pilot | 116,150,824 |
| Acquisition duration | 1,431.969 seconds, approximately 23.87 minutes |
| Acquisition peak process memory | 119,865,344 bytes |
| Header-only/zero-record files | 0 |
| Source whole-object CRC32 checks passed | 5,487 objects |
| Unsupported multipart composite CRC32 | 2 objects, customers and products |
| Local SHA-256 and structural evidence | All 5,489 objects |

Object reconciliation: 5,489 = 5,480 downloaded + 9 reused + 0 failed + 0 not attempted.
Byte reconciliation: 1,265,179,481 = 1,149,028,657 newly transferred + 116,150,824 reused.

| Table | Objects | Logical records |
| --- | ---: | ---: |
| customers | 1 | 150,000 |
| products | 1 | 400,000 |
| branches | 1 | 350 |
| service_agents | 1 | 1,200 |
| transactions | 1,097 | 4,425,008 |
| call_center_interactions | 1,097 | 686,296 |
| call_transcripts | 1,097 | 171,321 |
| complaints | 1,097 | 67,095 |
| satisfaction_surveys | 1,097 | 212,759 |

Each daily table spans observed partitions **2023-06-17 through 2026-06-17**, with no missing
calendar dates within that interval. Root tables have one object each and no inferred partition
history. Continuous observed dates do not establish upstream business completeness; the accepted
warnings remain `upstream_completeness_unproven` and `source_business_cutoff_unknown`.

Local evidence:

- Full acquisition run: `f84f68bccf3447528715fc1db38467d8` —
  [result](../../../outputs/extract/runs/f84f68bccf3447528715fc1db38467d8/result.json).
- Accepted full release: `624156a5cce033722fba62bd27fb2441227ca68395022c58aca1ce9bd3bb6be6` —
  [manifest](../../../outputs/extract/releases/624156a5cce033722fba62bd27fb2441227ca68395022c58aca1ce9bd3bb6be6/manifest.json).

The producing manifest preserves its original code fingerprint. Final checking-code refinements
were verified through the repeat run and recorded in that run's provenance; they did not
rewrite the immutable producing manifest or imply that CSV bytes changed.

The identical repeat passed with `unchanged`, exit 0: **all 5,489 objects reused**, zero downloads,
zero transferred bytes, 1,265,179,481 verified bytes and 6,114,029 logical records. It retained
the exact full release ID above while writing a new run result. Duration was **57.731 seconds**;
peak process memory was **137,019,392 bytes**. Reuse included hashing and structural revalidation;
this was not a cache-existence check. Failed and not-attempted counts were both zero.

Repeat run `a0869e86a4b64ef7994949759692b80c` —
[result](../../../outputs/extract/runs/a0869e86a4b64ef7994949759692b80c/result.json).
Its checking source-tree digest is
`a8cb34775cdc0d0876bda8443e7dbd771c73f83cbd61a75f899872aba620c56a`;
the full manifest's producing digest remains
`e85f6b46b57796f0865146ee0a8b5eb318616ca39856bddf681bcb0a89698219`.
The repeat result also records its contract, validation version and configuration digest.

Full offline verification passed with `verified`, exit 0, against the same full release:
**5,489 objects, 1,265,179,481 bytes and 6,114,029 logical records**. It transferred zero bytes,
reported zero failed/unattempted objects and took **40.515 seconds**, with peak process memory
of **106,774,528 bytes**. Its checking-code fingerprint matches the final repeat fingerprint.
Verification required no source connection or credentials.

Offline verification run `551b2d4839764bb7a2eaa8ec95d42587` —
[result](../../../outputs/extract/runs/551b2d4839764bb7a2eaa8ec95d42587/result.json).

| Acceptance action | Current evidence |
| --- | --- |
| Full historical acquisition | Passed; complete accepted release identified above |
| Identical full-history repeat | Passed; same release ID, all 5,489 objects reverified, no downloads |
| Full offline verification | Passed; all 5,489 local objects and manifest evidence verified, no source access |

All three full-history acceptance actions now have successful terminal results, rather than
being inferred from the presence of files.

Final handoff reconciliation also found exactly 5,489 stored CSV objects totaling 1,265,179,481
bytes, all with mode 0600; managed raw and output roots have mode 0700. The current full pointer
matches the release accepted by acquisition, repeat and offline verification. The temporary
process-authentication helper was removed; credentials were not saved.

## What the outputs provide

The raw object store preserves original CSV bytes. The accepted manifest identifies exactly
which source identities and local byte sequences form a delivery, with row counts, coverage,
checksums, contract version and code evidence. The current pointer publishes a whole accepted
scope atomically. Run plans and results account for work and preserve failures without exposing
partial datasets as complete releases. The `verify` action independently checks local usability.

These outputs allow later Transform work to start from an explicit, reproducible raw release.
They do not yet select card records, resolve joins or nulls, derive business states, establish
upstream completeness or populate a backend.

## User handoff, remaining decisions and limits

- The manual Extract pipeline and real-source acceptance are complete. Review this evidence
  before explicitly authorizing Transform; that phase has not begun.
- Future manual pulls require a standard AWS profile or process environment with authorized
  source credentials. This session used process-only authentication and did not save a reusable
  credential profile. Offline verification needs no credentials.
- The organizer has not supplied a completeness manifest or established a business cutoff and
  source timezone. Inventory reconciliation does not prove that all bank activity is present.
- Customer/product/agent root files do not establish historical snapshot semantics by themselves.
- Current durability tests cover the local POSIX/macOS behavior, not Windows or cloud-synced/network
  filesystem guarantees.
- Transform keys, joins, types, null handling, temporal meaning and card rules still need agreement.
  Load destination and strategy
  require their own agreement. No scheduling is enabled.
