# Validation evidence and limits

Snapshot: 2026-10-06 UTC. This is a synthetic engineering regression, not an untouched
acceptance set or a production safety estimate.

## Known integration blocker

**The currently published snapshots are not end-to-end compatible.** Frontend
`frontend/src/demo.ts` sends `selected_product_id` on every chat turn, including `null`.
The included backend's strict `SubmitTurn` contract lacks that field. Schema probes
with both `null` and a selected synthetic card fail with `extra_forbidden`; enabled
chat requests may therefore return HTTP 422. This is a confirmed contract mismatch,
not merely an untested behavior. Component tests, base readiness, and proxy startup
do not validate the complete product.

[Backend PR #7](https://github.com/yehosuah/FactoredAI_BCK/pull/7) tracks integration.
Its current published head is `bed5452e7fad96f4bc79e1c476ff2ab912f19ac1` and already
includes the missing `selected_product_id` contract field, but the PR is unmerged.
The tested local candidate includes further reviewed fixes whose publication remains
pending. That complete candidate is not this source snapshot or the PR's current head.
Frontend behavior has not been
silently reduced to accommodate the older backend.

The video MP4 delivered in chat uses the tested local candidate. It is evidence of
that local runtime, not proof that cloning this public snapshot reproduces the
recorded flow. A public video URL is still pending.

## Earlier local candidate regression

| Evidence | Result / provenance |
| --- | --- |
| ETL release | [PR #9](https://github.com/yehosuah/FactoredAI_base/pull/9), normal merge `c222173ee03df46be914cbfacfb097823f6a7196` |
| Reviewed ETL revision | `480aff81d9c01d1fb99819b97d2d95b4a8e3001a`; merged source tree matches this revision |
| Host checks | 378 tests and `make check` passed |
| Focused Linux checks | 53 process, oracle, and privacy tests passed |
| Synthetic integrated run | `pr9-receipt-regression`: 60 executed, 60 matched, 0 failed |
| Verified action evidence | Present in 6 evaluated cases |
| Unsafe outcomes | 0 observed in the 60 evaluated synthetic cases |
| Execution lanes | 40 classifier conversation, 8 controlled seam, 12 direct API cases |
| Harness / cleanup | No recorded error; disposable project stopped |
| Frozen reference checksum | `98ac934c5a9be2ecc9169c57ce216752153e138dbbe2731259a1a1293da84d43` |

The integrated run used backend `1a10dc3b567947bf44934a4f3e4982b6080ac2cf`, a **local,
unpublished candidate**. At this snapshot, public backend `main` was
`1e0321dc2c01ad5b4834183466b43f4563be18e4`. These revisions are different. The
60/60 result does not validate public backend `main` and cannot currently be reproduced
from the public repositories alone. Backend candidate publication remains a separate
pending decision.

Policy was tuned after earlier development failures, so this result has regression
status. Paired Spanish/Portuguese cases are not independent population samples;
controlled seams and direct API cases are distinct from classifier-driven conversations.
Zero observed unsafe outcomes does not establish zero risk, and the harness does not
exhaustively judge free-text truth. Source fixtures are team-authored synthetic data.

The author's earlier 44/60 run and subsequent 46/60 and 58/60 runs remain historical
evidence; the final regression does not erase them. The
[evaluation contract](https://github.com/yehosuah/FactoredAI_base/blob/main/docs/system-evaluation.md)
describes denominators, oracle repairs, and reporting limits.

Independent reviews of the exact ETL revision reported no major issues:
[security-focused review](https://github.com/yehosuah/FactoredAI_base/pull/9#issuecomment-6006961752)
and [code review](https://github.com/yehosuah/FactoredAI_base/pull/9#issuecomment-6007129428).
These reviews and test counts are evidence of the evaluated scope, not a production
certification.

## Consolidated source validation

The included remote-main snapshots were checked in the `etl/`, `backend/`, and
`frontend/` layout on macOS with Python 3.13.14, Node.js 25.9.0, and local PostgreSQL
18 tools. Original component bytes and dependency locks were preserved.

| Check | Result |
| --- | --- |
| Source provenance | 257 files match the source manifest, including Git blob identities and executable modes |
| Root installation | `make setup` passed with the three dependency locks |
| ETL checks | Lint, format, environment checks and 378 tests passed |
| Backend checks | Lint and format passed; 486 tests passed, one optional scikit-learn parity test skipped |
| Frontend checks | 65 tests passed; ESLint, TypeScript and Vite build passed |
| Frontend serving | Five configuration/local Nginx tests passed |
| Startup and proxy | Fresh base API readiness, frontend startup and root-command `/api` proxy passed; owned processes stopped |
| Compose layout | ETL/backend build contexts, bind sources and loopback API binding verified without starting containers |

Backend tests used `PYTHONPATH=src` so the non-editable test environment could locate
the included synthetic training corpus. Database tests used disposable local instances.
The fresh base API probe had data access disabled; it did not test login or confirmed
actions. A full Docker data/action runtime was not started for this consolidation check,
and existing recording/runtime services were not changed. These checks do not extend
the earlier 60-case regression to this different backend revision.

The unchanged frontend lock pins the development dependency `source-map-js` 1.2.1.
`npm audit` reports one high-severity advisory for malicious indexed source maps:
[GHSA-68fv-2mgg-jv7q](https://github.com/advisories/GHSA-68fv-2mgg-jv7q).
The project has released [patched version 1.2.2](https://github.com/7rulnik/source-map-js/releases/tag/v1.2.2).
Dependency remediation remains an upstream follow-up; this source snapshot does not
silently change the frontend's reviewed lock or claim a clean dependency audit.

## Publication audit

Before publication, all reachable advertised Git refs and GitHub discussion/review
metadata of the component repositories were scanned with checksum-verified Gitleaks
8.30.1. No confirmed credentials were found. Two backend detector hits were literal
conversation identifiers in unit tests, not session credentials. The classifier corpus
is marked `team_synthetic`; no organizer data files are included in this hub.

The original frontend repository stays private because four organizer PDFs remain in
its Git history and public redistribution permission is unverified. A clean frontend
source snapshot is included under `frontend/` here without those PDFs or Git history.
`source-manifest.json` identifies all three snapshots and every excluded file.
Automated scans do not prove that every possible secret is absent. Raw audit exports
and private evaluation records are retained locally and are not part of this public repository.
