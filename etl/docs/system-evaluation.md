# System evaluation contract

This small evaluator extends the portable synthetic demo. It is separate from the
72-case classifier corpus, its benchmark, training, weights and threshold selection.
The reference is the challenge synthesis in `docs/hackathon-brief.md` (challenge
pp. 3–6); original PDFs are not present in this checkout. These are team-authored
synthetic system references, not organizer records or independently adjudicated labels.

## Design and frozen references

The interface is one command and four artifacts. The reusable evaluation module owns
case validation, evidence scoring, metrics and reporting. Its runtime adapter owns
HTTP, demo ownership checks, persisted evidence and narrow deterministic fixture
controls. The only varying seam is the demo runtime; ordinary tests inject observations
without Docker. No workflow engine, model training or product behavior changes.

`evaluation/system-v1/cases.json` freezes 60 cases (30 ES, 30 PT), IDs, language,
reference outcome, automation eligibility, escalation label and measurement lane.
Its adjacent SHA-256 is checked before runtime creation. Cases were authored before
acceptance execution; no thresholds, model weights or routing policy may be tuned here.
Paired translations exercise the same requirements but are not independent samples.
References cover normal reads, selection, confirmations, receipts, cancellation,
persistence/retry, ambiguity, unsupported/credit/fraud/human escalation, queue fallback,
foreign/invalid cards, revoked/expired sessions, identity/confirmation/policy injection,
false-success prose, malformed input, tool failures and confirmation expiry/staleness.

Questions resolved against the challenge: containment is not resolution; preparation
is not action; assignment is not resolution; a model claim is not evidence. Wrong or
missing data must be detected by fixed fixture values and identity comparisons, not by
trusting another model or response prose. Direct API and injected-seam cases must remain
visible as separate evidence from classifier-driven conversations.

A case used to fix system behavior loses untouched-holdout status. Use `--purpose
regression` for subsequent verification and link pre-fix runs in the presentation.
Evaluator development runs are `development`; reserve `acceptance` for frozen code.
Changing a frozen reference requires a new version, not quietly changing its checksum.

## Metric definitions

All 60 cases are in scope. Numerators are case counts, never tool-call counts.
Safe automated resolution = reference-eligible, correct, safe outcomes with no persisted
handoff / all in-scope cases. Intermediate clarification/preparation and human-required
cases are not eligible. Correct policy refusals and cancellation can be eligible.
Automation attempt = at least one requested read/action tool or direct automated API
validation/operation; clarification alone and transfer-only turns are not attempts.
Containment = no persisted queued/assigned/accepted/resolved handoff, irrespective of
correctness. A queued record counts as escalation initiation, not completed human transfer.
Escalation quality reports correct (including useful matching context), missed,
unnecessary, and registered-but-incorrect routing/context; precision uses all registered
escalations and recall uses all reference-required escalations.

Unsafe outcomes count unauthorized disclosure, action without the explicit simulated
customer confirmation, and materially incorrect backend-verified outcomes. Zero must be
stated as "0 observed in N evaluated cases", never a claim of zero risk. Free model text
cannot satisfy success; its semantic truth is not exhaustively judged by this harness.
Latency uses linear-interpolated p50/p95 of completed cases and includes measured public
interactions/reconnect reads, excluding bootstrap, authentication setup, database audit,
fixture controls and cleanup. This is local/offline synthetic latency, not production.
External model/API cost is 0 only for verified local classifier/seam execution with no
provider. Infrastructure cost is `not_defined`. Unknown monetary costs stay `not_defined`.
ES/PT, measurement and execution lanes have separate slices. Conversation-only ES/PT
slices exclude direct API validation probes whose translated text is not processed. One synthetic segment cannot establish
a meaningful segment comparison. Small case counts are not population estimates.

Incomplete runs preserve the planned denominator, write partial evidence, mark status
incomplete, suppress acceptance rates/cost totals and exit nonzero. Reference failures
remain data and do not abort other cases. Harness/bootstrap/transport failures do abort.

## Safety and provenance

Only fresh `factored-eval-*` projects may be created; existing state/containers/volumes
are refused. The demo's local Unix Docker, ownership, secret-file and volume checks are
reused. No arbitrary target URL is accepted. Release provenance and exact fixture counts
are checked before executing any scenario. Backend checkout must be clean and match the
explicit SHA; built Python source/artifact hashes are checked against that checkout.
The ETL scheduler is stopped during evaluation to hold the release fixed, then resumed.
Reversible card changes are undone with explicit public confirmation; audit rows remain.
The project is stopped after evaluation while its private database volume is preserved.

Only projected IDs, status, counts, policy/tool/receipt metadata and boolean evidence
checks enter outputs; no raw customer rows, prompts/replies, credentials or exception
messages. Redaction is a second defense. Full evidence remains in the isolated backend.
Controlled session/confirmation expiry changes only this disposable fixture's timestamps.
The classifier cannot emit arbitrary answer prose or infrastructure exceptions: those
probes use the existing injected-adapter/store seams in a separate backend process with
real authorization, dispatcher, orchestration and persistence; no running adapter changes.

## Run

From the repository, with Docker Compose/BuildKit available and the exact independent
backend checkout selected under the integration policy:

```bash
uv run --locked --no-editable --reinstall-package factored-bank python scripts/evaluate_demo.py \
  --backend-path /path/to/reviewed/FactoredAI_BCK \
  --backend-sha <full-40-character-sha> --run-id acceptance-01 --port 18022 \
  --purpose acceptance
```

The command creates `outputs/evaluation/<run-id>/{run.json,case_results.jsonl,metrics.json,summary.md}`.
Both outputs and private `.demo/` state are ignored. Reusing a run ID/project is refused.
Each run records exact Base/BCK commits, source-tree/model hashes, descriptor, checksum,
UTC timestamp and configuration. A run's Base commit includes its harness implementation;
reporting-only commits after a run do not change the recorded evaluated candidate.
Ordinary `make test` does not require Docker. On macOS, if editable imports are stale,
run `uv sync --locked --no-editable --reinstall-package factored-bank` and then
`UV_NO_EDITABLE=1 make check` / `UV_NO_EDITABLE=1 make test`. Repeat the explicit
reinstall after source edits when testing a non-editable package. Complete checks: `make check`, `make test`,
`git diff --check`. Keep the PR draft pending independent review and reproducibility.

## Review repairs

Card oracles use frozen ETL revision-1 facts plus explicit simulator card facts,
with the release ID read from persisted state. The backend startup card response is
not ground truth. Consistently incorrect card balance, currency, status or other
projected fields fail both direct and conversation read checks.

Zero-case runs retain planned measurement and execution-lane denominators. Harness
or cleanup failure invalidates every slice and acceptance rate/cost, even after all
cases execute. Cleanup failure is recorded separately and flags manual cleanup while
retaining the original stable failure code. Supplied backend symlinks are refused
before resolution. Competing-action setup for stale confirmation is fixture control
time and is excluded from measured latency.

The author's run `acceptance-20261005-03` evaluated Base `fce3a2c4134de76d582ab22624fe56c5b99a115b`
and BCK `bed5452e7fad96f4bc79e1c476ff2ab912f19ac1`: 60 executed, 44 matching and 16 failing
references, with no verified action receipts. It remains evidence of that older
candidate. It does not validate these repaired oracles or prove the missing action
subpaths. Frozen references and model weights/threshold remain unchanged.

Movement oracles also use the complete frozen transaction projection, persisted
release identity, historical semantics and pagination facts. Source/build inputs
are checked against the requested Git tree, so ignored Python, JSON or native
modules cannot claim that commit's provenance. Container probe output is bounded
across stdout/stderr to 1 MiB with a 30-second subprocess deadline; failed children
are terminated before stable failure reporting and disposable-runtime cleanup.

The isolated development run `pr9-repaired-2202` recorded Base `685f291952d8a8c729bedd9c2c420d065e0972dc`
and the unmerged BCK candidate `7989789785e6e493ddb21bbf046a63ed886e7919`: 60 executed,
46 matching and 14 failing references, with zero action receipts. Both immediate
human requests matched; the remaining failures were the ES/PT prepare, confirm,
cancel, reconnect, retry, expiration and staleness references. The two pause
messages ranked reactivate first at 0.6017/0.6093. The direction-conflict guard
returned clarification before tool execution. This preserved run is development
evidence of that candidate, not proof of successful action subpaths or validated
safety. Later direct API workflow proofs are a separately labelled integration lane
and must not be counted as classifier resolution of these failing messages.


Base Docker inputs, mounted bootstrap scripts, the controller and frozen case file
are compared to their recorded Git blobs, including files hidden by skip-worktree
or Git ignore rules. Regression and acceptance require a clean verified Base;
dirty development runs explicitly have no verified Base-input digest. The mounted
BCK `deploy/handoff-read-grants.sql` is verified with the backend commit before use.
Failed probes terminate their entire process group even if the launcher exited.

The preserved `pr9-direction-regression` evaluated Base `30b0ed1ae0d2f080754b30609d0a3fc46e40a0c6`
and local, unmerged BCK `1a10dc3b567947bf44934a4f3e4982b6080ac2cf`: 60 executed,
58 matching and two failing movement-read references, with six cases containing
verified action evidence. All 12 direct API and eight controlled-seam cases matched.
The two failures arose because the evaluator expected the raw CSV empty merchant
string while the ETL contract and retained curated Parquet contain SQL NULL. This
run remains unchanged; its two reported incorrect verified outcomes are harness
oracle mismatches, not established backend data errors. A new run is required to
verify the repaired oracle. The BCK policy was tuned using prior development
failures, so subsequent evidence is regression, not an untouched acceptance sample.


Provenance Git commands disable local replacement objects: replacement refs cannot
substitute trees while retaining the recorded commit ID. Event tool errors persist
only recognized stable codes; unknown strings or objects become
`unrecognized_backend_error`, without copying backend exception text into reports.
The preserved `pr9-null-regression` at Base `97fe81f` completed 60/60 matches with six
cases containing verified action evidence and no harness/cleanup error. It remains
regression evidence for that head; subsequent provenance/error repairs require
fresh verification rather than relabelling that run.


Receipt fields now validate bounded ID formats and fixed contract enum/boolean
values before persistence. Invalid receipt values are replaced by stable markers
and cannot verify an action. Related copied identifiers and backend metadata also
use bounded projections, and all generated disposable-demo secrets participate
in redaction. None of these repairs changes the frozen case reference.
