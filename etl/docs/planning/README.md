# Team sprint: October 3-5, 2026

**Current readiness update (2026-10-04):** Read [readiness and Andrew's next task](readiness-update-2026-10-04.md). It supersedes the implementation/status snapshot below: backend latest `142608b`, local combined safety fixes pass 269 tests, ETL fixes pass 196 tests plus isolated Linux/PostgreSQL checks, and R1 is reserved for Andrew. No full sprint gate is accepted. Frontend remains excluded from this execution pass.

Start with the [full agent sprint plan](agent-sprint-2026-10-03-to-05.md), or read its [historical portable PDF](agent-sprint-2026-10-03-to-05.pdf) (October 3 snapshot; use the current Markdown update for dispatch). The [aggregate audit](audit-2026-10-03.json) preserves the measured findings, source revisions and SQL.

**Status:** proposed execution plan. Work packets are planned, not completed.
**Scope:** ETL, backend and frontend. ML implementation and benchmarking belong to the ML team; backend integration with its delivered interface is included.
**Calendar:** October 3-5, 2026, America/Guatemala. Dates are release checkpoints; dependencies and acceptance evidence control progression. October 5 is the requested planning horizon, not a verified event submission deadline.

## GitHub review update

Read the [branch/PR review](github-review-2026-10-03.md) and its [machine-readable evidence](github-review-2026-10-03.json). Verified account: `yehosuah`. There are no open PRs; ETL PR #2 and backend PR #1 are already merged. Unmerged ETL and backend branches contain useful work to reuse, while the frontend remains a starter.

The newest backend branch passed all 215 tests with disposable PostgreSQL. Three additional probes found an accepted-case recovery gap, terminal cases ahead of active queue work and contradictory receipts marked verified. Treat these as integration work in P00/P04/P08/P09/P10. The ETL candidate passed 187 tests and its profiler ran on the existing accepted release.

Start by pinning and reviewing the candidate branch chain, then reuse its profiler, optional ML packaging, tool dispatch, metrics and persistent cases. The full plan remains a proposed execution plan; branch implementation alone does not pass a packet's end-to-end gate.

## What we are building

One polished card-support experience in Spanish and Portuguese, with three demonstrable routes:

1. Confirm and execute a temporary card pause, then show the verified result.
2. Clarify an ambiguous block request before selecting a card or taking action.
3. Register an unrecognized-charge review request and produce a structured support case.

Every action is simulated, customer-scoped, confirmed where required and backed by an execution receipt. A registered request is not a refund, card shipment or fraud decision.

## Checkpoints

| Date | Required outcome |
| --- | --- |
| October 3 | Executable contracts, reproducible synthetic ETL-to-API boot, browser session/card context and the first verified action journey. |
| October 4 | Clarification, loss/theft handling, charge-review handoff, failure recovery, refresh/restart correctness and browser polish. |
| October 5 | Clean setup, accessible deployment, real ML integration acceptance, frozen evidence, public submission package, slides and mandatory demonstration video. |

## Start here

Andrew can start the bounded existing **R1 P08/P10 administrative recovery** slice now on backend `andrew/action-confirmation@142608b`. See the current update for isolated ownership, contracts and acceptance. P03 rationale documentation is an independent alternative. The remaining original full-packet dependencies still apply.

Start **P00: contracts and pinned revisions** and **P03: data rationale and quality evidence** in parallel. After P00, complete **P01: synthetic ETL-to-API boot**. Then P02, P04 and P10 can run in parallel with distinct frontend, conversation and pipeline ownership. P05 combines the first verified browser action journey.

Use one integration owner and up to three active worker agents. Each packet has one owner and isolated working state. The integration owner integrates changes serially and owns the shared acceptance stack. The full plan lists all sixteen packets, dependencies, acceptance details and reusable agent kickoff prompts.

## Repository map

| Repository | Responsibility |
| --- | --- |
| [FactoredAI_base](https://github.com/yehosuah/FactoredAI_base) | ETL, data contracts, fixtures, quality/freshness evidence and integrated runtime packaging. |
| [FactoredAI_BCK](https://github.com/yehosuah/FactoredAI_BCK) | Sessions, conversations, permissions, confirmations, tools, receipts, handoff and ML adapter. |
| [FactoredAI_FRT](https://github.com/yehosuah/FactoredAI_FRT) | React customer experience, ES/PT copy, typed API client and browser verification. |

Clones can live anywhere. Keep the repositories and environments independent, pin their revisions and integrate through the agreed contracts.

## External prerequisites

The final deployed release needs hosting access, a supported public TLS address, any required spending authorization, a compatible real ML delivery, the ML team's evaluation evidence and the submission team name. A stub-backed engineering pass does not complete the hackathon submission.

Live S3 activation remains deferred. Static historical inputs and labeled update fixtures are sufficient for this sprint's engineering demonstration.

The GitHub plan requires access to this private repository. The PDF and download bundle can be forwarded independently. Share the plan and aggregate evidence; organizer records, raw transcripts and credentials are not included.
