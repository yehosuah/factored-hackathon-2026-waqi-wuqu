# Validation evidence and limits

Snapshot: 2026-10-06 UTC. This is a synthetic engineering regression, not an untouched
acceptance set or a production safety estimate.

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

## Publication audit

Before publication, all reachable advertised Git refs and GitHub discussion/review
metadata of the component repositories were scanned with checksum-verified Gitleaks
8.30.1. No confirmed credentials were found. Two backend detector hits were literal
conversation identifiers in unit tests, not session credentials. The classifier corpus
is marked `team_synthetic`; no organizer data files are included in this hub.

The frontend stays private because four organizer PDFs remain in its Git history and
public redistribution permission is unverified. Automated scans do not prove that every
possible secret is absent. Raw audit exports and private evaluation records are retained
locally and are not part of this public repository.
