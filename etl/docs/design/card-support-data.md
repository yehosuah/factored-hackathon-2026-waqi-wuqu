# Card-support data scope and relationships

This is the current consumer-facing scope. The [Extract contract](extract-card-support/extract-v1-contract.md)
defines acquisition; its [verification report](extract-card-support/verification-v1.md)
records measured acceptance. The longer original design and its generated exports remain
local historical reference material.

## Supported prototype workflow

Debit/credit-card support covers loss/theft blocking, temporary pause/reactivation,
initial activation, replacement requests, card state/balance/limit/movements and
registration of unrecognized-charge requests for human review. Backend actions are
simulated. A replacement request does not imply issuance, shipping or branch stock.
Fraud adjudication, refunds, money movement, credit approval, limit increases and
PIN management are outside the approved scope.

ETL owns provenance and delivery. Backend owns authentication, customer isolation,
eligibility and verified action results. ML owns label review, model development,
evaluation and its consumer contract with ETL. A customer identifier alone is not authentication.
The independent backend checkout is not a runtime dependency of this ETL.

## Acquired tables and documented grain

| Table | Logical identity and grain | Time or interpretation limit |
| --- | --- | --- |
| customers | customer_id; customer | One delivered root CSV does not establish documented monthly snapshot history |
| products | product_id; customer product | Historical current_balance does not establish present available balance |
| branches | branch_id; branch | Opening hours do not establish replacement capability or inventory |
| service_agents | agent_id; human service agent | Status and shift do not establish live availability |
| transactions | transaction_id; movement | transaction_date is distinct from the daily process partition |
| call_center_interactions | interaction_id; contact | interaction_date is distinct from process_date |
| call_transcripts | transcript_id; transcript | No independent event timestamp is documented |
| complaints | complaint_id; case | Creation and subsequent lifecycle dates have different meanings; revisions need a rule |
| satisfaction_surveys | survey_id; response | survey_date is distinct from interaction and process dates |

These are dictionary identities, not approved historical deduplication keys. All input
values are preserved as text. Raw storage preserves original CSVs and source versions;
the accepted manifest, rather than a directory scan, defines release membership.

## Dictionary relationships

Required means the dictionary documents a non-null child field. It does not assert
that the received data passed a business-integrity check.

| Child field | Referenced parent | Required |
| --- | --- | --- |
| customers.registration_branch_id | branches.branch_id | Yes |
| products.customer_id | customers.customer_id | Yes |
| products.opening_branch_id | branches.branch_id | Yes |
| transactions.customer_id | customers.customer_id | Yes |
| transactions.product_id | products.product_id | Yes |
| transactions.branch_id | branches.branch_id | No |
| service_agents.assigned_branch_id | branches.branch_id | No |
| call_center_interactions.customer_id | customers.customer_id | Yes |
| call_center_interactions.agent_id | service_agents.agent_id | No |
| call_transcripts.interaction_id | call_center_interactions.interaction_id | Yes |
| call_transcripts.customer_id | customers.customer_id | Yes |
| call_transcripts.agent_id | service_agents.agent_id | Yes |
| satisfaction_surveys.interaction_id | call_center_interactions.interaction_id | No |
| satisfaction_surveys.customer_id | customers.customer_id | Yes |
| satisfaction_surveys.agent_id | service_agents.agent_id | No |
| complaints.customer_id | customers.customer_id | Yes |
| complaints.affected_product_id | products.product_id | No |
| complaints.related_branch_id | branches.branch_id | No |
| complaints.origin_interaction_id | call_center_interactions.interaction_id | No |
| complaints.assigned_agent_id | service_agents.agent_id | No |

There is no explicit complaints.transaction_id. Matching by amount/customer/date would
be an inference requiring agreement. mentioned_products is text, not a validated
relationship table. No one-to-one interaction/transcript/survey constraint is assumed.
The transcript/interaction join was profiled separately for the accepted release;
that result does not certify every relationship above.

## Temporal and ML constraints

Event time, process date, source modification time and ingestion time remain distinct.
Source timezone and business snapshot cutoff are unknown. Later fraud labels, resolutions,
compensation, satisfaction scores and complete conversations can leak outcomes into inputs.
Feature eligibility and reserved splits must follow the experiment's decision boundary.

Policies and operational action traces are separately governed sources. Agent replies
are not authoritative policy. The team-synthetic Spanish/Portuguese review cases have
separate provenance from the organizer's synthetic Spanish transcripts.
See the [ML quick start](../ml-handoff.md) and [consumer design](ml-handoff/README.md).
