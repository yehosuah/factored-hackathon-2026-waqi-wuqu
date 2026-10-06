# Portable synthetic demo

This standalone runtime prepares and publishes all nine ETL tables from **invented team
fixtures**. It requires no organizer files, AWS credentials, model weights or model API.
The default backend conversation adapter is the deterministic engineering stub, visibly
labelled as such in the frontend. A separately reviewed backend can opt into its packaged
local learned classifier as described below. Historical fixture cards and all card actions
remain simulated in either mode.

## Start

Requirements: Docker with BuildKit, Docker Compose with `up --wait`, a non-root host
account and a local Unix Docker endpoint, Python 3 for the bootstrap wrapper, and an independent backend checkout that
contains the conversation adapter and `deploy/handoff-read-grants.sql`. The images use
their own locked Python 3.13 environments; this ETL image uses digest-pinned Python
3.13.16 and the independent backend selects its reviewed image. Host dependency
installation is optional. See [image audit and maintenance](image-audit.md).

The ETL production image uses the locked native Psycopg client linked to vendor libpq
and OpenSSL; compiler/header packages stay in the builder. Local `uv sync --locked`
keeps the development binary client. ETL, fixture and grant jobs use a read-only root
filesystem, no-new-privileges, dropped capabilities and private noexec/nosuid `/tmp`.
Only the declared state mounts are durable and writable. Size temporary storage for
the workload. PostgreSQL bootstrap has its own required privilege lifecycle.

From this repository:

```bash
git clone https://github.com/yehosuah/FactoredAI_BCK.git FactoredAI_BCK
# Check out the separately reviewed backend integration commit if it is not on main.
python3 scripts/demo.py up --backend-path ./FactoredAI_BCK
python3 scripts/demo.py status --backend-path ./FactoredAI_BCK
```

`--backend-path` may point to any independent reviewed checkout; the helper never
fetches, resets or modifies that repository. Default project `factored-demo` binds only
`http://127.0.0.1:8010`. PostgreSQL port 5432 stays inside Compose. The frontend should
proxy same-origin `/api/*` to that loopback API and strip `/api`; permissive CORS is not
required. Existing live/history Compose configuration is unchanged.

## Local learned classifier

The trained artifact and loader belong to the independent backend. Once its classifier
integration has passed review, use that reviewed checkout and explicitly select it:

```bash
export DEMO_CONVERSATION_ADAPTER=classifier
python3 scripts/demo.py up --backend-path ./FactoredAI_BCK
```

The backend image includes `src/factored_bck/intent/intent_model_v1.json`; inference loads
those JSON weights locally, with no external provider or credentials. The helper refuses
an unavailable classifier artifact or unknown adapter selection before building,
recreating or verifying the runtime. Existing-container management remains available
regardless of a changed shell selection or unavailable checkout artifact.
This setting must remain exported for later `up`, `rebuild-backend` and `verify` commands;
without it the explicit default is `stub`. It does not reset private state or grant new
database privileges. For an existing project, keep its configured backend checkout path
and have the backend owner fast-forward that clean checkout to the reviewed merged code.
The helper continues to refuse silently redirecting an existing project to another path.
Reported `conversation_adapter` comes from the running backend container, including
for `status` and `restart`; it is `null` when no backend is running. Changing the shell
selection does not change a running container through `restart`. Use the coordinated
`rebuild-backend` command to apply a new selection.

The live conversation descriptor must report `provider=intent-classifier`,
`version=intent-tfidf-lr-v1`, `mode=injected`. A successful ETL ML review-pack publication
is a separate data handoff and does not establish that this learned adapter is running.
The classifier-mode verifier checks this descriptor, the `get_movements` tool and owned
card identity, and the complete result against a direct published-movements HTTP read
for actual ES/PT natural-language requests. These are functional integration fixtures, not a
certified held-out benchmark; use the separate disposable proof project below.

Generated raw, accepted Extract manifests, curated Parquet and secrets are private under
`.demo/<project>/`, excluded from Git and both images. PostgreSQL uses a separate
`<project>_demo-postgres` volume. Six generated passwords are never printed or placed in
Compose environment values. ETL, backend and bootstrap services use the non-root host
owner UID/GID. Existing secrets are retained; a missing existing secret fails rather than
silently rotating a database password. Changing backend path, port or owner requires a
new project name, so an existing runtime is not silently redirected. Remote Docker
endpoints and same-named Compose projects from another checkout are refused.
The retained PostgreSQL volume is checked even after `down` removes its containers.
A private `volume-owner.json` binds its immutable identity to this checkout/state;
initial adoption requires this project's PostgreSQL container with the matching
private password-file mount. A containerless volume without that ownership record is
refused; use a new project name. Volume labels/configuration are preserved so Compose
does not request database recreation during upgrades.

Bootstrap order: fixture -> healthy PostgreSQL -> existing ETL scheduler with an explicit
offline manifest -> backend-owned narrow handoff grants -> fixture account provisioning
-> healthy backend. The grant script uses the existing strict `NOLOGIN` reader role;
ETL refreshes retain it. Bootstrap checks every published release is this synthetic
fixture before granting or provisioning. It must not be used to change grants in an
existing non-demo database without explicit administrator authorization.

## Private accounts and data

Read the corresponding local file privately; never paste passwords into shared logs.

| Account | Login | Private file under `.demo/<project>/secrets/` |
| --- | --- | --- |
| First customer | `demo` | `demo_password` |
| Second customer | `demo-other` | `other_demo_password` |
| Separate human agent | `demo-agent` | `agent_password` |

`demo` owns published card `DEMO-CARD-001` and three accepted historical movements, plus
the backend's four explicitly labelled simulator cards. `demo-other` owns
`DEMO-CARD-OTHER`, which the first customer's session cannot access. The accepted agent
`DEMO-AGENT-001` is an Active Digital Specialist with Español/Portugués and fraud
specialty. Assignment is not evidence of live availability, acceptance or resolution.
The default release contains 13 accepted rows across all nine tables, with no ML pack.

The backend stub supports `/cards`, `/pause <owned-card-id>`, `/clarify` and `/handoff`
through its conversation API. Only the explicit customer confirmation HTTP endpoint
commits an action. Agent accept/resolve requires its separate agent session.

## Prove failure, refresh and restart

Use a **separate disposable proof project**, because this verifier intentionally changes
synthetic source bytes, commits reversible simulator actions and restarts its services:

```bash
python3 scripts/demo.py up --project factored-demo-proof --port 18011 \
  --backend-path ./FactoredAI_BCK
python3 scripts/demo.py verify --project factored-demo-proof --port 18011 \
  --backend-path ./FactoredAI_BCK
python3 scripts/demo.py down --project factored-demo-proof --port 18011 \
  --backend-path ./FactoredAI_BCK
```

The proof checks actual password-authenticated roles and narrow grants, real published
card/movement HTTP reads, customer/agent isolation, ES/PT handoff assignment and
accept/resolve, conversation reads in the selected adapter mode, corrupted-input rejection retaining the accepted
release, recovery/cache reuse, corrected publication with stale-cursor rejection, and
PostgreSQL/ETL/backend restart persistence for sessions, receipts and conversations,
then full project stop/recreation retaining its private secrets, grants, accounts and volume.
During source-corruption and publication proofs, it stops the regular ETL scheduler
and uses isolated one-shot ETL containers, so the 300-second cycle cannot compete for
the publication lock. It resumes the scheduler even if a proof raises an error.
It restores fixture revision 1 and the tested card's original reversible simulator
state. Audit and conversation evidence remain available; it reports only aggregate
check names, never tokens, passwords or rows.

After the browser owner releases a coordinated window, update only the backend image:

```bash
python3 scripts/demo.py rebuild-backend --backend-path ./FactoredAI_BCK
```

This rebuilds/recreates only the backend service; ETL, PostgreSQL, secrets, fixture
accounts and evidence remain in place. Recheck its ready endpoint before resuming the
browser. Never run it during another owner's active browser journey.

`down` stops only that project and preserves its volumes and private state. `restart`
restarts only PostgreSQL, ETL and backend for the named project. No command deletes an
existing volume or rewrites organizer data. The scheduler already runs every 300 seconds;
no separate scheduler or live S3 polling is introduced by this demo.

## Tested boundary

Measured locally with Docker 29.2.0, Compose 5.0.2 and Linux Python 3.13.14 images.
Backend candidate `782133e` was built from the separate owner's checkout and passed the
full thirteen-check runtime proof, including the backend-only image rebuild. Its model
integration remains a separate team responsibility. The classifier-mode thirteen-check
proof also passed with the actual packaged learned artifact in backend candidate
`07b7b86dd97b2eeedca68397b923079ab73156c8`, using a separate disposable project.
This establishes local functional integration at that candidate, not acceptance of
subsequent backend changes or activation of an existing shared runtime.
The frontend owner proves browser rendering and interaction against the loopback API.
