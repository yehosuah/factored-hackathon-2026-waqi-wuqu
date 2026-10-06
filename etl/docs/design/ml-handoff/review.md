# ML handoff review

Date: 2026-09-29, America/Guatemala. Status: awaiting design and content review.

## What is ready to inspect

The [portable review pack](../../ml-handoff.md) contains assistant-authored,
explicitly synthetic draft inputs for all three experiments in Spanish and Portuguese:
16 policy documents, 72 intent cases, 20 retrieval queries and 16 summary cases.
The [contract proposal](README.md) records source evidence and the delivery boundary.

An isolated-directory load of the zipped pack passed checksum, size, count, key,
taxonomy-reference, policy-context and evidence-reference checks. All records remain
drafts. No split, language-quality certification or evaluation approval is asserted.
Current recipient evidence: `outputs/ml-handoff-review/2026-09-29/recipient-validation.json`.
The portable archive is `outputs/ml-handoff/review-pack-v1.zip`.
That small archive contains only synthetic review materials. The separate
`outputs/ml-handoff/exploration-v1.tar.gz` includes the complete pinned organizer raw
release, the review pack, loading instructions and locked runtime sources.

## Proposed simulator policies

These are fictional rules for the team simulator, not real bank policies. The complete
Spanish/Portuguese wording is in `data/fixtures/ml-handoff-v1/policies.jsonl` (private local file).

| Policy | Proposed behavior |
| --- | --- |
| Identity and access | Require test-session authentication and product ownership. A customer ID alone does not prove identity. Expired sessions require reauthentication; another customer's product is not exposed. |
| Loss/theft blocking | Clarify ambiguous block requests. Confirm blocking only from a verified successful tool result. A loss/theft block cannot be automatically reactivated in this proposal. |
| Pause/reactivation | ACTIVE can be paused; PAUSED can be reactivated. BLOCKED, EXPIRED and CLOSED do not permit automatic reactivation. Confirm the resulting state from tool evidence. |
| Initial activation | Only an owned PENDING_ACTIVATION card is eligible under the proposed simulator contract. Missing eligibility or a failed tool result cannot be reported as activation success. |
| Replacement | A successful request registration means a request exists. It does not establish issuance, shipping, delivery or branch stock. Unknown prices and dates remain unknown. |
| Read-only context | Preserve currency and the available cutoff. Report a credit limit only when applicable and verified. Unknown amounts remain unknown; historical values are not presented as current. |
| Unrecognized charge | Identify the customer's transaction, then register evidence for human review. Registration does not establish fraud or authorize a refund. |
| Escalation | Separate requests, attempted actions, verified outcomes and unresolved questions. A failure or unknown outcome is never summarized as completion. |

The state names above are proposed simulator vocabulary. Mapping organizer product
statuses to them needs a separate Transform contract; it must not be assumed.
Policy effective dates and review owners are unset in the draft corpus.

## Routing decisions exposed by the examples

The agreed starting taxonomy has ten categories. Examples deliberately expose:

- Lost card plus unrecognized charge: two requests, potentially different workflows.
- Pause plus movements: an action and a read request in the same utterance.
- Reactivation after a theft report: request intent differs from action eligibility.
- “Block my card”: insufficient evidence to choose loss/theft versus temporary pause.
- Unknown product: a clarification need, not a confident card-action instruction.

The user accepted multiple intent labels, clarification for ambiguity and prioritizing
loss/theft before other requests. Draft route targets now apply that rule; individual
annotations remain unreviewed. The pack does not perform any action.
Request classification must not be mistaken for authorization or eligibility.

The user also accepted the proposed lifecycle rules: reversible temporary pause,
no automatic reactivation after loss/theft blocking, PENDING_ACTIVATION for initial
activation, and request-only confirmation for replacement. These are design agreements;
they do not certify every policy translation or example annotation.

## Review requirements before scored evaluation

1. A policy owner reviews and accepts the fictional rules and their versions.
2. ML reviewers check each label, relevance annotation and summary required/forbidden fact.
3. Spanish and Portuguese reviewers check meaning and wording in their language.
4. ML agrees independent held-out cases, grouping, coverage, metrics and thresholds.

Paraphrases and translations are grouped together in the draft. They are not
independent observations. The review pack demonstrates contract shape and failure
cases; it does not supply a statistically credible benchmark by itself.
Human review results must identify their reviewer and source/annotation version.
Design agreement does not automatically mark every example or translation reviewed.

## Remaining delivery work

The portable raw layer and exploration package passed a recipient test in a fresh
extracted directory with its own locked uv environment: all 5,489 raw objects and
6,114,029 logical records verified offline, and Polars loaded all 171,321 transcripts.
Organizer-derived initial-request inputs still require an evidence-backed parsing
boundary; reviewed independent cases remain a separate source.
Full evaluation readiness and backend action-trace integration remain distinct gates.
No external transmission, shared-storage connection or backend changes were made.

For local handoff, extract the exploration archive into a private directory. With a
POSIX terminal, set `umask 077` before extraction. Then follow its root `README.md`:
`uv sync --locked` and offline verification of the pinned release. The raw originals
and draft experiment data have separate manifests and readiness states.
