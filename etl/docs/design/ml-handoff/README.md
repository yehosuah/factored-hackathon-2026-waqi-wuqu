# ML handoff: contract proposal

Date: 2026-09-29, America/Guatemala.
Status: design in progress. This document proposes contracts; it does not report
implemented Transform, an accepted curated release, approved labels or approved policies.

## Outcome and agreed scope

The ML team can independently load a pinned raw release and curated datasets for
intent routing, card-policy retrieval and human-handoff summarization. Each example
has traceable evidence, an explicit readiness state and an appropriate evaluation split.
The user requested all three experiments and both raw and curated delivery.

The next design round accepted a portable local first delivery, the ten starting
intent categories below, and assistant-authored synthetic policies and Spanish/Portuguese
cases for human review. The [portable review pack](../../ml-handoff.md) implements
that drafting step only. Its labels, translations and policy rules remain unapproved.

The scope remains debit/credit-card support as defined in the
[existing design](../card-support-data.md).
This work starts consumer-contract design. Transform implementation depends on settling
its source, output and preparation rules. Backend implementation remains in its own repo.

## Established evidence

The accepted full raw release is
`624156a5cce033722fba62bd27fb2441227ca68395022c58aca1ce9bd3bb6be6`.
Fresh offline verification passed for 5,489 objects and 6,114,029 logical records;
`make check` and 100 tests passed. Raw acceptance checks bytes and CSV structure,
not business correctness or fitness for ML.

An aggregate profile of all transcript/interaction objects found:

| Measure | Observed |
| --- | ---: |
| Transcript rows / distinct transcript IDs | 171,321 / 171,321 |
| Exact distinct customer_text values | 42 |
| Exact distinct full_text values | 546 |
| Rows with recorded detected_language = es | 171,321 |
| Transcript interaction IDs absent from interactions | 0 |
| Customer-ID mismatches in that join | 0 |
| Customer-text values associated with multiple recorded contact reasons | 42 |
| Exact distinct first customer lines in full_text | 2 |
| Rows with multiple customer lines | 68,577 |

The evidence is private local aggregate metadata in
`outputs/ml-handoff-review/2026-09-29/profile.json`, ignored by Git.
Exact duplicate counts do not measure semantic diversity; recorded language is not
independent language validation. This is not a comprehensive quality audit.
The observed repetition and reason ambiguity mean row counts and source-derived labels
cannot establish an independent intent benchmark.

## Proposed raw delivery contract

Deliver the pinned accepted manifest, manifest digest and all referenced original
objects, preserving their relative paths. Include the dependency lock, verification
instructions, data dictionary, known limitations and consumer loading example.
Do not expect another checkout to resolve this machine's absolute paths.
The manifest is the membership boundary; arbitrary raw-directory scans are unsupported.
Raw access does not imply permission to send complete records to an external model.
The destination and transfer/access method are open decisions.

## Proposed common curated envelope

Every dataset declares its schema/contract version and row grain. Proposed common fields:

| Field | Meaning |
| --- | --- |
| example_id | Stable identifier under the agreed preparation rule |
| source_kind | Organizer synthetic, team synthetic or reviewed application event |
| source_refs | Raw release/object/record references or a separately versioned team source |
| language | Reviewed example language, with method and review status |
| review_status | Draft or reviewed; only reviewed cases can enter scored evaluation |
| split | Development, validation or held-out test under a versioned assignment |
| leakage_group_ids | Duplicate/template/scenario and relevant entity grouping references |

Source event time, process date, ingestion time and decision cutoff remain separate.
Unknown timezones or snapshot cutoffs remain unknown; S3 LastModified is not event time.
ML payloads contain only the fields permitted by the experiment contract. Source references
may resolve to restricted raw storage without including private source values in logs.

## Intent dataset proposal

Grain: one customer request as available before the routing decision.
Additional fields: request_text, intent_label, taxonomy_version, label_source,
annotation_version and review evidence. Organizer contact_reason/detected_intents
remain separate candidate annotations, not automatically accepted ground truth.
The rule for identifying an initial request must be reviewed before deriving examples:
customer_text may include later dialogue, and full_text may expose the answer.

Proposed starting intents: block lost/stolen card, pause card, reactivate card,
activate card, request replacement, query card status, query balance/limit,
query movements, register unrecognized-charge request, and unsupported/unclear.
The user accepted these as the starting taxonomy. Whether balance/limit should be
separate labels remains a refinement decision.
The user accepted multiple intent labels, clarification when ambiguous, and loss/theft
priority before other requests. Routing does not establish authorization or eligibility.

## Policy retrieval dataset proposal

Grain: one version of an approved policy document; retrieval evaluation is a separate
query-to-relevant-policy dataset. Proposed document fields: document_id, policy_version,
approval_status, jurisdiction, card_type, language, effective_from, effective_to,
content_ref and checksum. Each evaluation query records applicable context, expected
document references and whether no applicable policy is the correct result.

Policy contents and their owner need agreement. If the team authors synthetic rules,
their simulated status must remain explicit. Agent replies are not policy authority.
ETL preserves approved originals and provenance. ML owns chunking, embeddings, indexing
and retrieval experiments, with versions sufficient to reproduce results.

## Handoff summary dataset proposal

Grain: one case as available at the moment of escalation.
Additional fields: conversation_ref, decision_cutoff, verified_tool_results,
unresolved_questions, evidence_refs, required_facts and forbidden_claims.
Tool-result fields must distinguish attempted, succeeded, failed and unknown outcomes;
their detailed event schema is a consumer agreement with the backend team.

Transcript-only summarization and action-grounded summarization have different readiness.
Historical text alone cannot verify an action by our simulator. Synthetic action fixtures
can support early experiments if explicitly identified and reviewed. Application traces
are a separately contracted source, not silently inferred from historical CSVs.

## Preparation and acceptance proposal

1. Pin and verify all source releases; validate source contracts before preparing data.
2. Define effective keys, null tokens, types, time semantics and card inclusion rules.
3. Preserve duplicate membership/provenance; agree treatment without rewriting raw history.
4. Validate joins and reconcile inputs to published examples, exclusions and rejects.
5. Assign evaluation splits without duplicate/template leakage. Entity and temporal
   isolation are chosen per experiment; do not blindly combine constraints that leave
   too few independent examples. Report conflicts and per-split coverage.
6. Publish the complete curated candidate only after its checks pass; retain the previous
   accepted release on failure. Repeat preparation must preserve logical output identity.
7. Record source IDs, code/contract/annotation/policy versions, output checksums, counts,
   split definitions, quality results and limitations in a curated release manifest.
8. Verify that an independent ML consumer can load the package, reproduce counts and
   trace an example. This remains an acceptance action, not an achieved result.

Development cases may be exploratory. Scored model comparisons need reviewed labels,
independent held-out cases and identical benchmark inputs for baseline/model comparison.
Portuguese examples need separate sourcing or reviewed team creation and provenance.
Metric definitions and acceptance thresholds belong to the ML experiment contract.

Proposed readiness states: raw_verified, exploration_ready and evaluation_ready,
reported separately for each experiment and language. A bundle can expose all three
experiments without asserting that each has evaluation-ready data.

## Open decision frontier

- The user accepted reversible pauses, no automatic reactivation after loss/theft blocks,
  PENDING_ACTIVATION for initial activation and request-only replacement confirmation.
  Review of complete policy wording, translations and effective-date semantics remains open.
- Review individual route targets under the accepted multi-intent/clarification rule.
- Evaluation review ownership: independent case creation, annotation and language review.
- Later preparation decisions: split constraints, case coverage, experiment metrics,
  initial-request extraction and action-event schema.

No policy contents, labels, split percentages, minimum case counts or business thresholds
are invented by this proposal. No external transfer or connection is configured.
