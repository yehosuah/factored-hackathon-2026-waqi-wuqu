# FactoredAI: readiness update and Andrew's next task

2026-10-04 UTC. This updates the existing October 3–5 sprint at
`yehosuah/hackathon-agent-sprint@7df807a`. This supplement is prepared for a separate docs-only draft PR.
No changes were merged or deployed and no teammate messages were sent. Frontend is excluded
from the current execution pass. The original cross-repository gates still apply.

## Start now: existing R1, P08/P10 handoff recovery

**Reserved for Andrew (`A625A`).** This is the smallest independent part of the
already-recorded R1 finding; it does not claim the full P08/P10 packets are ready
or complete. No R1 implementation was added by the security task.

| Item | Concrete instruction |
| --- | --- |
| Repository/base | `FactoredAI_BCK`, `andrew/action-confirmation@142608b51706ca2637e3e8ba815379ed21d3c9e6`; use a new isolated local branch |
| Existing work | All four Andrew backend commits are present: metrics, tools, persistent cases/agent auth and prepare/confirm actions. Untouched latest `make check`: 250 tests pass |
| Defect | Assigned → accepted; disable or invalidate assigned agent; resolution is 401, customer cancellation is 409, local-admin reroute is 409 because reroute supports queued cases only |
| Deliverable | An authorized, audited local-admin recovery operation for stranded assigned/accepted cases, reusing deterministic routing and preserving existing case history/evidence |
| Own files | `handoff_store.py`, `handoff_admin.py`, `handoff_schema.py`, dedicated recovery tests, `docs/human-handoffs.md` |
| Dependencies | Existing PostgreSQL fixture and source contract; no conversation, frontend, provider or ML runtime is needed for this bounded recovery slice |
| Conflict boundary | Current security fixes touch Store/routes/security/pagination/tools/agent_auth/evidence and separate tests; avoid modifying those files while recovery is in progress |
| Not authorized | Customer/model-selected target agent, banking mutations, public admin route, production data, push/merge/deploy or teammate messages |

Acceptance:

- Disabled-agent and accepted-release-driven ineligibility can be recovered safely.
- Recovery records prior status/agent, reason, administrative provenance, source
  release and time; preserve existing verified evidence and lifecycle history.
- Queued routing still uses the existing policy, with no arbitrary target override.
- Resolved/cancelled cases stay terminal; unsupported recovery returns a conflict.
- Acceptance/resolution/recovery races serialize and cannot yield two incompatible
  committed transitions. Recheck authority/eligibility at the operation boundary.
- Customer and model transports cannot invoke recovery. Use private synthetic
  PostgreSQL fixtures and run the backend's full `make check`.

Follow-up R2 active/manual queues remains separate. Alternate independent work, if
R1 is unavailable, is the existing **P03 workflow-rationale report** (`Blocked by:
Nothing`) on ETL `andrew/ml-routing-evaluation@de0d3ea`; reuse the profiler, do not
build ML. Pinned historical release `a5ea7a8613c31883cf7c9173f0c541b12c49fd291f0d594432fc798d1c3bf5f4`
and `docs/design/card-support-data.md` / historical planning audit provide context.
Use aggregate limitations; do not turn 1,547,408 card transaction rows or 77,712
declines into support demand, or 143,852 transcript rows with 42 distinct customer
texts/546 full texts into independent conversations. Keep freshness/provenance explicit.

## Current branch and fix state

GitHub identifies both author and committer of all four backend commits as `A625A`.

| Candidate | State versus main | Reuse / remaining work |
| --- | --- | --- |
| BCK `main@d6aa84a` | Accepted PR #1; no later main fixes | Three review regressions confirmed and fixed locally: secret rotation, full-order movement cursor, unknown-username scrypt timing |
| BCK `andrew/backend-observability@bd2e74a` | 1 ahead / 0 behind | Reuse bounded process-local HTTP metrics and committed-action aggregates |
| BCK `andrew/backend-tools@8328d74` | 2 / 0 | Reuse typed authenticated dispatcher |
| BCK `andrew/human-handoff-routing@fd40d2c` | 3 / 0 | Reuse persistent cases, deterministic policy, agent auth/lifecycle; R1/R2 open |
| BCK `andrew/action-confirmation@142608b` | 4 / 0; contains preceding three | Reuse server-owned pending commands and atomic confirmed receipts; full conversation host remains absent |
| ETL `main@dbb32f5` | Accepted PR #2; no later main fixes | Four review findings confirmed |
| ETL `andrew/ml-routing-evaluation@de0d3ea` | 3 / 0 | Reuse profiler, optional ML, symlink hardening. This is profiling/packaging, not an intent router or scored ML runtime |
| ETL planning `yehosuah/hackathon-agent-sprint@7df807a` | 2 / 0 | Documentation only; this update is based here |

Backend standalone fixes: **35 tests pass**, full `make check`. They are published
as [backend draft PR #2](https://github.com/yehosuah/FactoredAI_BCK/pull/2), commit
`6e8269c9f97d0519d1daeab3145932cce407a157`, targeting `main@d6aa84a`.
Local combined latest teammate + fixes: **269 tests pass**, full `make check`.
This includes agent-login timing hardening and sprint **R3**: contradictory state
receipts fail for pause/block/activate/reactivate; valid receipts/replays remain valid.
Agent timing and R3 fixes remain only in the uncommitted combined checkout; they
are not included in backend draft PR #2. R1 is reserved for Andrew.

The combined PostgreSQL journey runs as `backend_api`: customer/agent isolation,
HTTP-to-tool cursor paging, all six preparations/confirmations, idempotent replay,
fraud handoff assignment/acceptance/resolution, metrics, source permission refresh,
retained simulator state/evidence/cases/sessions and denied contact-column reads.
Tests use private disposable clusters and controlled fixtures, not a deployed stack.

ETL fixes are published separately in [ETL draft PR #3](https://github.com/yehosuah/FactoredAI_base/pull/3),
head `3a45c9916e849cf7dfbf3974422d408a8c7d7f2b`. It preserves the three original
A625A teammate commits plus the fixes, and excludes sprint documentation.

ETL worker evidence: full checks plus **196 tests**, real Linux UID permission
regression and **7 isolated PostgreSQL 17.11 publication scenarios** pass. Its patch
applies cleanly to `de0d3ea`, reuses existing symlink hardening and adds full-scope
gating, process-date parent coherence, explicit nonroot host owner mapping and
regular-metadata manifest integrity. These results are from the ETL task, not
independent backend retesting.

## Contracts and integration gates

- Data: unchanged `card-support-etl-v1`, complete immutable nine-table candidates,
  authoritative PostgreSQL `bank.current_release`, separate persistent `simulator`.
  Source grains/ownership remain strict; timestamps are historical, not live balances.
- Profiler: `factored-profile --release current` uses a read-only accepted-release
  lookup; explicit curated IDs report publication `not_checked`. Private atomic
  `outputs/profiles/<curated_release_id>/profile.json`, schema `1.0.0`, includes
  provenance/reconciliation/tables/card-support/transcript/survey/temporal metrics,
  modeling risks and limitations. It does not return action authorization.
- Optional ML pack: `team-ml-review-v1`, `0.1.0-draft`, `draft_review_only`.
  No approved policies/backend executions/scored evaluation. Optional omission is
  `ml.readiness=not_included`; metadata/datasets must belong to the checksummed pack.
- Action contract: existing card route and mutating tools now **prepare**; execution
  requires a separate authenticated customer confirmation ID. Check
  `status=executed`, `verified=true` and committed evidence. Never give the model
  raw bearer credentials, arbitrary HTTP or confirmation capability.
- Handoff grants: base readiness can pass without `customers.segment` / service-agent
  access. The teammate `deploy/handoff-read-grants.sql` fixes the gap locally through
  inherited minimum-column grants, which survive ETL direct-grant reset. Run
  `python -m factored_bck.handoff_admin check` under the actual backend role before
  enabling the handoff journey. No grants were applied to an existing deployment.
- Fresh integrated acceptance remains open: clean-clone synthetic nine-table boot,
  fixture movements/agents, source-aware provenance, isolated visitor state,
  Compose setup with private host-owned mounts and restricted roles, restart and
  refresh persistence. Separate component passes do not close this gate.
- Conversation ownership/history, delivered provider adapter, turn/attempt/evidence
  links and human-event confirmation integration remain P00/P04/P05 work. Reuse the
  existing primitive; do not create a second tool/action implementation.

## Local deliverables and next integration

Within `/Users/yhimp/Documents/Codex/2026-10-03/task-4`:

- `BACKEND_HANDOFF.md`: full backend evidence, fixes, readiness limits and ETL contracts.
- `backend-security/`, `codex/backend-security-review`: committed main-based fixes
  in backend draft PR #2; the teammate feature stack is excluded.
- `backend-ready-integration/`, `codex/backend-ready-integration`: complete local
  integration based on `142608b`, with one Store import conflict resolved and cursor
  tool/agent timing/R3 validation additions.
- `backend-security.patch` applies to `d6aa84a`; `backend-ready-integration.patch`
  applies to `142608b`. Use the appropriate complete patch, not both cumulatively.
- `sprint-handoff/`, `codex/hackathon-handoff-update`: updated existing planning
  README, plan and branch-review pointers, plus this supplement. Historical audits
  and PDF remain unchanged and are explicitly labeled historical.

ETL deliverables live in `task-3/ETL_HANDOFF.md` and `task-3/etl-security-fixes.patch`.
Integrate original teammate history first, then its matching local patch, verify both
component suites, wire restricted preflight/provisioning and perform the fresh isolated
Compose acceptance. The user authorized draft PR publication for verified-ready code and documentation.
Merge and deployment remain unauthorized. The ETL worker owns its separate code PR;
this docs branch changes only `docs/planning` and does not publish teammate code.

Installed skills used: `improgress-desarrollo` **0.2.0** (behavioral red→green tests),
Toolkit **0.3.0** (`afinar` skill metadata **0.4.0**, already-settled scope), and local
`achiever-mode`. No branding, Plan de sesión or plugin installation was applied.
