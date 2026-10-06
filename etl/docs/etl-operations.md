# ETL and backend operation

The [approved contract](design/etl-system/contract.md) defines preparation, quarantine,
release publication and simulated card support. Compose builds two independent images
and runs PostgreSQL on an internal network. Organizer inputs, Parquet outputs and
credentials are runtime mounts, excluded from both images and Git.
The [verification record](design/etl-system/verification.md) separates measured offline
acceptance from the live-source activation requirement.

## Start the local historical prototype

From the workspace root, with both repository checkouts available:

```bash
uv sync --locked
uv run --locked python scripts/init-secrets.py
uv run --locked python scripts/init-etl-state.py
export ETL_UID=$(id -u) ETL_GID=$(id -g)
ETL_OFFLINE=true docker compose up --build -d
docker compose ps
```

Run the setup as the non-root host account that owns the ETL state. Compose requires
`ETL_UID` and `ETL_GID` explicitly and runs ETL with that numeric owner. The helper creates
`data/raw`, `outputs/extract` and `data/processed` privately before bind mounting, and
checks existing ownership/access without changing it. This lets ETL read its mode-0600
Extract objects and write locks, status and releases on Linux. Do not make private data
world-readable or run the scheduler as root. If existing state belongs to a different
account, run as that owner and use its UID/GID; the helper deliberately does not chown it.
Export the same mapping in any later shell before using Compose, including the ML overlay.
Standalone `docker run` deployments likewise need `--user <owner-uid>:<owner-gid>`; the
image's fallback UID 65532 is intended for storage owned by that UID.

The same host-owner mapping lets the backend read its private runtime secrets.
PostgreSQL starts its standard root bootstrap, copies only its three required password
files into mode-0600 files in a private tmpfs owned by the PostgreSQL UID, then runs its
standard entrypoint to drop privileges. The host files remain read-only and unchanged;
no credential is placed in Compose environment values or images. Role initialization
fails on unreadable or empty passwords instead of creating passwordless application roles.
Initialization scripts only run for a new PostgreSQL data directory. Existing roles
with missing or incorrect passwords require an authorized administrative repair;
changing secret files does not reset stored passwords or existing database state.

Startup verifies the accepted local raw manifest, prepares all nine tables without
an ML pack by default, then loads PostgreSQL. The API is
live while preparing but readiness returns 503 until a complete release is committed.
Initial preparation and loading take several minutes. Use `docker compose logs -f etl`
and `uv run --locked factored-etl status` to observe aggregate progress.

`ETL_OFFLINE=true` is explicitly offline: it verifies the historical input and tests
scheduled execution, but does not discover S3 updates. With no accepted raw input,
run the existing Extract CLI first or start with configured S3 credentials.

## Enable live source checks

Keep AWS credentials in a private standard AWS credentials/config file. Do not put
access keys in Compose YAML, command arguments, committed files or image build args.
Configure runtime paths and, if necessary, a profile:

```bash
export ETL_AWS_CREDENTIALS_FILE=/absolute/private/path/credentials
export ETL_AWS_CONFIG_FILE=/absolute/private/path/config
export AWS_PROFILE=default
ETL_OFFLINE=false docker compose up -d etl
```

The ETL service checks the agreed S3 inventory every five minutes and does a full
offline reconciliation daily. The daily marker advances after successful publication.
There is no overlap or burst catch-up. An unchanged input reuses verified prepared
files and loaded rows. Corrections preserve prior releases. Failure keeps the old
database pointer, marks the run failed, makes ETL health unhealthy and retries on the
next cycle. A running phase older than 30 minutes also fails the ETL health check.

Temporary AWS credentials must include their session token and be refreshed before
expiry. The code does not manufacture or renew credentials. Source discovery is not
verified merely because offline delivery or an HTTP health endpoint passed.

## Consumer and runtime checks

```bash
curl -f http://127.0.0.1:8000/health/ready
uv run --locked python scripts/verify-publication.py
uv run --locked python scripts/verify-system.py
uv run --locked python scripts/verify-consumer.py
uv run --locked python scripts/verify-restart.py
```

The publication check uses an isolated temporary PostgreSQL database and invented
fixtures. It tests complete loading, unchanged repeat, correction, rollback before
commit and subsequent recovery. It removes only the database it created. The API check
creates isolated team fixtures, tests sessions, customer isolation, concurrent
idempotency, supported/ineligible states and audit evidence, then removes its fixtures.
The independent reader copies the accepted directory, verifies every checksum/count and
privately traces a record to its original CSV. The restart check exercises a temporary
team card action, restarts ETL/backend and verifies the action and audit after a cached
ETL repeat. All checks report aggregates without credentials, tokens or organizer rows.

The generated `.secrets/demo_password` authenticates username `demo`. Read that local
file privately and use `/auth/login` in [Swagger](http://127.0.0.1:8000/docs).
Use Swagger's **Authorize** button with the login token. Card methods require
`Authorization: Bearer <token>`; action methods also
require a distinct `Idempotency-Key`. The demo account owns four labeled team cards;
an additional other-customer fixture must return 404. No source customer is implicitly
authenticated by knowing a customer ID. Provision source-customer test accounts with
the backend's `factored-provision --password-file` command inside its own environment.

Historical cards show masked numbers, recorded balance/currency and explicit historical
semantics. Blocking, pausing/reactivating and activation mutate only simulator state.
Replacement confirms request registration only. An unrecognized-charge request requires
the customer's exact transaction ID and process date and registers human review only.
`/me/handoff` returns committed simulated results; `/operations/etl` returns aggregate
release and run metadata to authenticated test sessions.

## Parquet and ML delivery

The PostgreSQL `bank.current_release` pointer is authoritative. Its manifest identifies
the directory `data/processed/releases/<release_id>/`. An operator can verify that
portable directory without S3 or database access:

```bash
uv run --locked factored-etl verify --release-dir data/processed/releases/<release_id>
```

Every accepted table has a matching `*.rejects.parquet` containing original text and
reasons. These are private source records, never logs or public artifacts. Counts
reconcile input = accepted + rejected. All rows preserve object checksum and one-based
logical source-record ordinal; resolve raw references through the pinned Extract
manifest. Optional money remains null, currencies remain separate and no conversion
or current-balance inference is performed.

Only accepted Extract manifests whose complete scope definition and scope ID match
`full` may prepare an authoritative candidate. A nine-table `pilot` is rejected before
any prepared-cache reuse. Interaction references in transcripts, surveys and complaints
must match `(interaction_id, process_date)` and customer ownership; an accepted parent
on another date cannot satisfy or conceal a missing/quarantined same-date parent.

When explicitly included, the `ml/` folder contains the existing ES/PT draft policy,
intent, retrieval and handoff datasets, contract and taxonomy. The enclosing manifest supplies checksums, counts,
source kinds and `exploration_ready` status. Original review/approval states remain
unchanged; no labels, language quality, independent splits or scored benchmark are
certified. Typed organizer tables remain a separate exploration source.

Included ML packs must list `contract.json`, `taxonomy.json`, `README.md` and the four
JSONL datasets as exact manifest members with their bytes and SHA-256. The source
manifest itself is pinned by the curated identity and source-manifest checksum; it
cannot checksum itself. Every copied file is checked for symlinks before reading. Directory descriptors are pinned
and `O_NOFOLLOW` rejects path swaps when opening each component. Validation and curated
checksums use the exact staged bytes, so a swap cannot replace validated metadata.
Only regular files are permitted; FIFOs and other special files are rejected before reading
so a supplied pack cannot indefinitely block the scheduler.
Older packs that omit metadata membership must be reissued by their owner with these
checksums, or explicitly omitted using the optional ML configuration. Existing immutable
releases are left intact; this change does not approve draft annotations or translations.

## Optional ML pack and offline preparation

An organizer release is complete without the draft ML pack. With neither `--ml-root`
nor `ETL_ML_ROOT` set, `run`, `serve` and `prepare` pass no ML source and record
`"ml": {"readiness": "not_included"}`. No `ml/` directory is produced. The profiler
uses the accepted organizer Parquet tables and works with either kind of release.

```bash
# Prepare from a pinned, verified local raw manifest; no PostgreSQL or S3 needed.
# Leave ETL_ML_ROOT unset for organizer-only delivery.
uv run --locked factored-etl prepare --manifest outputs/extract/releases/<raw_release_id>/manifest.json

# Explicitly include an existing reviewed-for-use draft pack (not a scored benchmark).
uv run --locked factored-etl prepare --manifest <manifest> --ml-root /private/ml-pack

# End-to-end publication requires the configured PostgreSQL service.
uv run --locked factored-etl run --offline
```

A nonempty `ETL_ML_ROOT` is also an explicit request. `--ml-root` takes precedence.
Unset the variable to omit ML; an empty/whitespace path is a configuration error,
not an alias for the working directory. Explicit missing, unreadable or invalid packs
fail the run and never fall back to organizer-only publication. Existing checksum,
count, taxonomy/reference and draft-review checks remain in force. Package contents,
including its copied README, participate in input identity; same pinned raw input,
code, lock and configuration reuse the same release. Adding or changing the pack
changes identity. Organizer validation, row counts and Load semantics are unchanged.

Compose's base file no longer mounts or requires a draft pack. To include one, use
the opt-in override; the host path must already exist (Compose must not create it):

```bash
ETL_ML_ROOT=/absolute/private/ml-pack ETL_OFFLINE=true \
  docker compose -f compose.yaml -f compose.ml.yaml up --build -d etl
```

The override maps that host path read-only to `/ml-input` and sets the container's
`ETL_ML_ROOT` accordingly. A host variable alone does not opt the base Compose file
into ML delivery. Existing operators relying on automatic inclusion of
`data/fixtures/ml-handoff-v1` must now supply `--ml-root`, `ETL_ML_ROOT`, or this override.
Prepared candidates remain distinct from PostgreSQL-published releases.

## Recovery and stop

```bash
docker compose restart backend
docker compose stop
# Start again with the same offline/live choice; volumes retain data and simulator state.
ETL_OFFLINE=true docker compose up -d
```

Stopping/restarting does not erase PostgreSQL, original CSVs or prepared releases.
Do not use `docker compose down -v` as a routine restart: it deletes database state.
A partial load rolls back and cannot switch the accepted pointer. If PostgreSQL commit
succeeds but writing `current.json` is interrupted, the database still serves the
accepted release; a repeat repairs the local mirror. A damaged prepared file prevents
publication instead of silently reusing it. Keep reject and run evidence for diagnosis.

Both images run as non-root; PostgreSQL has no host-published port, the API binds to
localhost, the ETL role cannot write simulator state and the API role cannot modify
source tables or read transcript tables. Test authentication and the local network
configuration implement the hackathon prototype contract; they are not an attestation
of a production bank deployment.
