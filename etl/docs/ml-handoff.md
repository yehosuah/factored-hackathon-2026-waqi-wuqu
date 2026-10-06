# ML engineer quick start

The handoff enables exploration of intent routing, policy retrieval and escalation
summaries. The organizer raw release is verified; the team-synthetic examples, policies
and translations are drafts. Reviewed held-out evaluation data is a separate next step.

## Files to send

| File | Purpose |
| --- | --- |
| `etl-source.bundle` and `etl-source.bundle.sha256` | Cloneable Git history for `yehosuah/ml-handoff`, including the locked runtime, Extract, tests and consumer contracts |
| `exploration-v1.tar.gz` and `exploration-v1.tar.gz.sha256` | Complete raw release plus draft synthetic experiment inputs and loading instructions |

The ETL remote is [yehosuah/FactoredAI_base](https://github.com/yehosuah/FactoredAI_base).
The original handoff branch was merged and removed. Clone the current ETL `main`:

```bash
git clone --branch main https://github.com/yehosuah/FactoredAI_base.git factored-etl
```

Record `git rev-parse HEAD` with any new validation. The source bundle remains a
historical offline alternative with its original `yehosuah/ml-handoff` branch;
it does not include subsequent ETL security, optional-pack or demo runtime fixes.
All bundle/archive artifacts live under `outputs/ml-handoff/`, outside Git.
Data archives travel separately through the team's permitted channel.
These paths identify the historical handoff; they do not guarantee the artifacts are
present in a fresh checkout. Obtain the permitted archive and verify its checksum
before following the archive-specific setup below. Do not download organizer data or
manufacture missing artifacts to satisfy these instructions.

## Runtime model boundary

This handoff contains draft data and contracts. It contains no trained weights,
model loader, inference service or certified held-out evaluation. The quality profiler
and optional ETL ML pack do not deploy a model.

`--ml-root` / `ETL_ML_ROOT` opts into the existing synthetic **review pack**. Its inputs
are `manifest.json`, `contract.json`, `taxonomy.json`, `README.md`, and four JSONL files:
`policies.jsonl`, `intent_cases.jsonl`, `retrieval_cases.jsonl`, `handoff_cases.jsonl`.
ETL validates provenance, membership, bytes, checksums, counts, identities and references,
then includes those exact bytes under the curated release's `ml/` directory.
The output remains `approval_status=draft_review_only` and
`scored_evaluation_authorized=false`. `exploration_ready` means the review data was
packaged successfully; it does not mean a trained component is running. Without an
explicit pack, `ml.readiness=not_included`; an explicitly missing or invalid pack fails.

The independent backend owns any learned adapter and its startup contract. A usable
model handoff must identify the actual artifact, immutable checksum/version, loader and
dependency versions, allowed input/output schema, training/evaluation provenance, and
missing/corrupt-artifact behavior. Verify real loading and inference in that consumer
before describing it as deployed. Artifact absence is a blocker, not permission to
label a stub, evaluator or data review pack as a learned model.

Send the branch link and the exploration archive plus its checksum. Send the source
bundle/checksum only when an offline checkout is needed. The smaller `review-pack-v1.zip`
is optional because the exploration archive already contains those draft inputs.

## Recipient setup

Requirements: Git, uv and a supported local POSIX filesystem. uv selects Python 3.13.
Initial dependency installation may need internet access. Raw verification needs no AWS credentials.

For the offline alternative, place the four files in one directory, then run:

```bash
shasum -a 256 -c etl-source.bundle.sha256
shasum -a 256 -c exploration-v1.tar.gz.sha256
git clone --branch yehosuah/ml-handoff etl-source.bundle factored-etl
umask 077
mkdir -p ml-data
tar -xzf exploration-v1.tar.gz -C ml-data
cd factored-etl
uv sync --locked
make check
make test
uv run --locked factored-extract verify \
  --scope full \
  --release-id 624156a5cce033722fba62bd27fb2441227ca68395022c58aca1ce9bd3bb6be6 \
  --raw-root ../ml-data/exploration-v1/data/raw/organizer \
  --output-root ../ml-data/exploration-v1/outputs/extract
```

Expected raw verification: `status: verified`, 5,489 objects, 1,265,179,481 verified
bytes and 6,114,029 logical records. Retain the raw release ID in experiment metadata.
The archive's root README includes a manifest-based Polars raw loading example.

## Load the draft experiment inputs

From the `factored-etl` checkout, this standard-library example checks membership and
loads the intent cases without treating their draft annotations as ground truth:

```python
import hashlib
import json
from pathlib import Path

root = Path("../ml-data/exploration-v1/datasets/team-synthetic")
manifest = json.loads((root / "manifest.json").read_text())
assert manifest["readiness"] == "draft_review_only"
for entry in manifest["files"]:
    raw = (root / entry["path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
    if entry["path"].endswith(".jsonl"):
        assert len(raw.decode().splitlines()) == entry["record_count"]

intent_cases = [json.loads(line) for line in (root / "intent_cases.jsonl").read_text().splitlines()]
assert len(intent_cases) == 72
assert all(case["split"] is None for case in intent_cases)
print({"draft_intent_cases": len(intent_cases)})
```

The package also contains 16 draft policy documents, 20 retrieval queries and 16
handoff-summary cases. Each experiment has Spanish and Portuguese inputs.
Synthetic action-result assertions are fixtures, not backend execution traces.

The repository versions the [consumer contract](design/ml-handoff/contract.json),
[starting taxonomy](design/ml-handoff/taxonomy.json), [design](design/ml-handoff/README.md)
and [review sheet](design/ml-handoff/review.md). Individual experiment records live in
the separate archive and local ignored `data/fixtures/ml-handoff-v1/` directory.

## First ML work

1. Load and inspect the three draft datasets; identify contract or label problems.
2. Review policy wording, Spanish/Portuguese text, relevance labels and summary facts.
3. Define independently authored held-out cases, split constraints and baseline metrics.
4. Compare baseline and learned approaches on the same reviewed cases once ready.

The organizer transcripts have 171,321 rows but only 42 exact distinct `customer_text`
values and two distinct first customer lines under the observed role-marker format.
Source contact reasons are not accepted ground truth. These findings require care with
duplicate/template leakage and show why row count alone does not justify an intent benchmark.

The agreed routing approach allows multiple intent labels, clarifies ambiguity and
prioritizes loss/theft before other requests. Request intent does not establish action
authorization or eligibility. The fictional simulator uses reversible pauses, no automatic
reactivation after a loss/theft block, PENDING_ACTIVATION for initial activation and
request-only confirmation for replacement. Full organizer Transform rules remain pending.

## Message to accompany the files

> Here's the ETL starter handoff for routing, card-policy retrieval and escalation summaries.
> Clone main of yehosuah/FactoredAI_base and follow docs/ml-handoff.md.
> The separate archive contains the
> complete verified raw release and Spanish/Portuguese draft experiment inputs. Please
> start with loading and exploratory baselines, review the labels/policies/translations,
> and define independent held-out cases and leakage-safe splits before reporting scores.
