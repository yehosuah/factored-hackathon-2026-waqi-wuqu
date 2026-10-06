# GitHub branch and PR review - October 3, 2026

**Current readiness update (2026-10-04):** Read [readiness and Andrew's next task](readiness-update-2026-10-04.md). It supersedes the implementation/status snapshot below: backend latest `142608b`, local combined safety fixes pass 269 tests, ETL fixes pass 196 tests plus isolated Linux/PostgreSQL checks, and R1 is reserved for Andrew. No full sprint gate is accepted. Frontend remains excluded from this execution pass.

Reviewed through GitHub CLI authenticated as **yehosuah (Yehosua Hercules)**. Snapshot: October 4 at 04:18 UTC, October 3 at 22:18 America/Guatemala. The three established repositories are ETL (`FactoredAI_base`), backend (`FactoredAI_BCK`) and frontend (`FactoredAI_FRT`); the workspace's ETL is the repository interpreted from the request's "CTO" reference.

**Decision:** reuse the ETL candidate and the backend branch chain, with the fixes and integration gates below. The implementation is a useful foundation, but the browser-to-conversation-to-confirmed-action demonstration is still missing. No application code was changed or merged during this review. The only published change is this guide and its exports. ML implementation remains excluded.

## Inventory and verdicts

There are **zero open PRs** in each repository. All nine remote branch heads were inventoried. The implementation PRs remembered in the request are already merged. Links and commit IDs below pin the reviewed code rather than promising that future branch contents are identical.

| Repository / branch | Reviewed revision | Assessment |
| --- | --- | --- |
| ETL `main` | `dbb32f5` | [PR #2](https://github.com/yehosuah/FactoredAI_base/pull/2) merged October 2: strong publication/reconciliation foundation. Historical live-stack results remain historical. |
| ETL `andrew/ml-routing-evaluation` | `de0d3ea` | Three unmerged commits: aggregate dataset profiler, optional ML pack and auxiliary-file hardening. Despite its name, this diff is ETL/data-quality work; no model implementation. Recommend integration after normal PR/CI review and synthetic boot acceptance. |
| ETL `yehosuah/hackathon-agent-sprint` | `94ebbe5` before this guide update | Documentation and portable planning artifacts only; no additional system implementation. |
| BCK `main` | `d6aa84a` | [PR #1](https://github.com/yehosuah/FactoredAI_BCK/pull/1) merged October 2: authenticated cards, historical movements, simulated actions and persistence. Good foundation, incomplete conversational product. |
| BCK `yehosuah/card-support-integration` | `e59182c` | Already contained in main; the one-commit difference is main's merge commit. Do not schedule this as new implementation. |
| BCK `andrew/backend-observability` | `bd2e74a` | One unmerged commit: bounded HTTP timing/counts and committed-action aggregates. Useful engineering instrumentation with explicit limitations. |
| BCK `andrew/backend-tools` | `8328d74` | Contains observability plus controlled tool dispatch. Useful authenticated seam; fix contradictory receipt acceptance before consuming it as proof of execution. |
| BCK `andrew/human-handoff-routing` | `fd40d2c` | Contains both preceding branches plus persistent cases, agent sessions, deterministic routing and lifecycle. Useful implementation; request changes for recovery and queue behavior, then complete deployment/conversation integration. |
| FRT `main` | `95a1a43` | Only remote branch and no PR history. Buildable ES/PT starter; no chat, API client, login, confirmations, receipt or support experience. |

ETL [PR #1](https://github.com/yehosuah/FactoredAI_base/pull/1) is also merged, on September 30. Its draft ML-pack review state was checked as an ETL consumer dependency; model quality was not reviewed. The reviewed code heads have no GitHub check runs; ETL/backend candidate combined statuses contain zero status contexts. A returned `pending` state with zero contexts is **absence of a CI signal**, not an observed failing job.

## Findings to revisit

### R1 - P1: accepted handoffs can become stranded

[Agent authentication](https://github.com/yehosuah/FactoredAI_BCK/blob/fd40d2cb5a4fe6142aae776a3742f57ae8eebf9f/src/factored_bck/agent_auth.py#L83) denies disabled or newly ineligible accounts. That is correct access revocation. But [case transitions](https://github.com/yehosuah/FactoredAI_BCK/blob/fd40d2cb5a4fe6142aae776a3742f57ae8eebf9f/src/factored_bck/handoff_store.py#L231) prohibit customer cancellation after acceptance, and [administrative reroute](https://github.com/yehosuah/FactoredAI_BCK/blob/fd40d2cb5a4fe6142aae776a3742f57ae8eebf9f/src/factored_bck/handoff_store.py#L262) only permits `queued` cases.

**Reproduced on disposable PostgreSQL:** create -> assigned -> accepted; disable its assigned account; agent resolution returns 401, customer cancellation returns 409, administrative reroute returns 409. The case remains accepted with no supported recovery operation. Source refresh can cause the same eligibility failure; that refresh variant was inferred from the shared eligibility check, not separately exercised.

**Required:** an authorized, audited reassignment/requeue recovery path that preserves case history and cannot be driven by the model or customer. Test disabled accounts, release-driven ineligibility and concurrent lifecycle transitions. Owner: BCK, P08/P10.

### R2 - P2: terminal cases occupy the active queue

[Handoff listing](https://github.com/yehosuah/FactoredAI_BCK/blob/fd40d2cb5a4fe6142aae776a3742f57ae8eebf9f/src/factored_bck/handoff_store.py#L199) sorts by priority and oldest creation without excluding terminal states. It is valid as case history, but insufficient as the agent work queue required by the sprint.

**Reproduced:** resolve a case, create a new case at the same priority, fetch `/agent/handoffs?limit=1`; the resolved case appears first and the assigned case moves to the next page. High-priority terminal history can similarly hide lower-priority open work.

**Required:** separate active queue from history using an explicit status filter or active-first ordering, with pagination tests. Unassigned cases also need a restricted operational queue view: current customer/agent transports cannot provide a global manual-review queue. Owner: BCK/FRT, P08.

### R3 - P2: contradictory action state is labeled verified

[Dispatcher receipt validation](https://github.com/yehosuah/FactoredAI_BCK/blob/fd40d2cb5a4fe6142aae776a3742f57ae8eebf9f/src/factored_bck/tools.py#L212) checks action, product, simulated status and outcome, but accepts any state from the broad state enum. This behavior is also present in `backend-tools`.

**Reproduced at the Store seam with a controlled adapter:** `pause_card` receives a receipt whose action is `pause` and whose state is `ACTIVE`; the result is `ok=true, verified=true`. The unit suite also uses a PAUSED receipt for several different state-changing tools. This is a validation weakness at the adapter seam, not evidence that the real Store currently commits incorrect state transitions.

**Required:** match state-changing action receipts to their expected states: pause -> PAUSED, block -> BLOCKED, activate/reactivate -> ACTIVE. Keep request-only semantics for replacement/charge review. Add contradictory-state and valid-replay checks. Owner: BCK, P04/P05/P09.

## Integration gaps that tests do not close

- **Deployment grants and readiness:** handoff code reads `bank.customers.segment` and `bank.service_agents`. The existing ETL backend grants do not include these columns. The branch supplies a least-privilege inherited-role [SQL script](https://github.com/yehosuah/FactoredAI_BCK/blob/fd40d2cb5a4fe6142aae776a3742f57ae8eebf9f/deploy/handoff-read-grants.sql), but it is a separate administrative step, absent from current integrated Compose boot. `/health/ready` still checks only the Store release; it does not invoke `check_configuration()` for handoff access. Wire preflight/provisioning into reproducible boot and prove failure when required grants are absent. Do not solve this with table-wide grants.
- **Conversations and confirmation:** tool dispatch is internal and synchronous; it is not a chat transport or an ML runtime. Mutating tools have no server-owned pending-confirmation contract. Build P04/P05 around them, authenticate outside model context, and offload synchronous calls from async orchestration.
- **Case scope:** persistent cases now capture summary, context and unresolved questions, with model claims separated from allowlisted committed evidence. They still take up to 20 customer/card actions, with no conversation ID or failed/unknown attempts. Reuse the case module and add conversation-scoped links; do not claim P08 is complete.
- **Demo data and provenance:** optional ML packaging removes one private-file prerequisite. It does not create the complete nine-table synthetic boot, fixture movements, isolated visitor state or source-aware backend provenance. The bank-products query still hardcodes `organizer_synthetic` for ETL-published products; fix this before serving team-generated ETL fixtures.
- **Measurements:** HTTP percentiles cover recent process-local samples up to response headers. Counters reset on restart; workers do not share them. Persistent aggregates count committed actions/cases, not attempted failures, model cost, containment or safe resolution. P11 still needs turn/tool outcome tracing, end-to-end timings and denominators.
- **Frontend and release:** all browser work, integrated clean-clone CI, public TLS deployment and submission artifacts remain outstanding. The three repositories are private; publication of the final safe submission repository is still a planned gate.

## Validation performed

| Revision | Evidence from this review |
| --- | --- |
| ETL `de0d3ea` | `make check` passed; `make test`: **187 passed**, no duplicate test copies in the isolated checkout. Profiler CLI succeeded on the existing accepted Parquet release without changing data or publication pointers. |
| BCK observability `bd2e74a` | Lock/lint/format checked; **48 passed, 7 skipped** on this tip. Explicit Ruff checks used `--no-respect-gitignore` because the archive lived under an ignored review-output directory. |
| BCK tools `8328d74` | Lock/lint/format checked; **112 passed, 21 skipped** on this tip, with the same explicit Ruff handling. |
| BCK handoff `fd40d2c` | `make check`: **172 passed, 43 skipped** with default local-binary fixture. Then **215 passed, zero skipped** with disposable PostgreSQL 17.11. Only infrastructure-fixture selection was adapted; original application and test assertions were unchanged and restored afterward. Two additional PostgreSQL probes reproduced R1/R2; a controlled-adapter probe reproduced R3. |
| FRT `95a1a43` | `npm run check` passed: lint, TypeScript build and Vite production build. Browser workflow acceptance remains pending because no workflow implementation exists. |

Temporary databases used invented fixtures only, bound to localhost, with no customer datasets mounted. Containers were removed. These results are not a new public-deployment or integrated Compose acceptance pass.

The profiler independently confirmed 6,114,029 input = 6,020,768 accepted + 93,261 rejected rows. It found **1,547,408 ownership-consistent card transaction rows**, including **77,712 recorded declines (5.022%)**. This is historical transaction activity, not measured card-support demand or recoverable revenue. Accepted transcript data has **42 distinct customer texts across 143,852 rows** and **546 distinct full texts**; these aggregate data-quality observations must not be presented as independent conversation volume. No transcript text or individual identifier is included in this guide.

## Revised agent dispatch

1. **P00 / integration:** pin ETL `de0d3ea`, BCK `fd40d2c`, FRT `95a1a43` as candidate revisions, with main revisions separately recorded. Review/fix R1-R3, reconcile handoff grants and readiness, and prepare application PRs through the team's normal workflow. Main stays the accepted baseline until integration gates pass.
2. **P03 / data:** reuse `factored-profile`; preserve the accepted-release/profile revision and aggregate report. Finish workflow rationale, product-mention attribution limitations and freshness evidence rather than rebuilding the profiler.
3. **P01 / data-runtime:** reuse optional ML packaging. Add the missing synthetic ETL release, movement/provenance support, restricted grants, agent account provisioning and isolated public-demo boot.
4. **P04 / service:** reuse ToolDispatcher and typed case interfaces; implement owned persistent conversations and the delivered ML adapter. **P05** adds authoritative confirmation and the verified browser pause.
5. **P08 / service-experience:** extend persistent cases with conversation/attempt references, R1 recovery, R2 active/manual queues and the support view. **P09/P10** validate R3, unknown outcomes and refresh/restart continuity.
6. **P11-P15 / acceptance-release:** reuse backend instrumentation while collecting missing system-level evidence, completing frontend polish, clean-clone CI, provider-neutral deployment and the required slide/video package.

The October 3-5 calendar, dependency gates, work-in-progress cap and exclusion of ML development remain in force. No packet is marked complete merely because a branch contains part of its implementation.
