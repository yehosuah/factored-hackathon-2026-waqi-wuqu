# Consolidated source and local setup

All three component source trees are included. No separate private repository clone
or submodule initialization is required. Requirements: Git, `make`, `uv`, Node.js
24 or newer, and npm. Python 3.13.14 is managed by each locked Python environment.
Docker Engine/Compose is needed only for the optional synthetic runtime.

```sh
git clone https://github.com/yehosuah/factored-hackathon-2026-waqi-wuqu.git
cd factored-hackathon-2026-waqi-wuqu
make verify-sources
make setup
make check
```

`make setup` installs from `etl/uv.lock`, `backend/uv.lock`, and
`frontend/package-lock.json`. The first installation needs internet access.
`make check` runs ETL environment/lint/format/tests, backend lint/format/tests,
and frontend tests/lint/TypeScript/build. Environments remain separate. Backend checks
set `PYTHONPATH=src` so its source-relative synthetic training corpus is found when
using a non-editable installation.

Backend PostgreSQL regressions require `initdb` and `pg_ctl` in `PATH`; otherwise
those tests are skipped. On macOS with PostgreSQL 18 from Homebrew:

```sh
PATH="/opt/homebrew/opt/postgresql@18/bin:$PATH" make check
```

These tests create private disposable local PostgreSQL instances. They do not use
an existing database. `make etl-check`, `make backend-check`, and
`make frontend-check` run the components separately.

One optional backend scikit-learn parity test is skipped without the `ml` dependency
group; classifier inference does not require that group. To run this optional test:

```sh
cd backend
PYTHONPATH=src uv run --locked --group ml --no-editable pytest tests/test_intent_model.py
```

## Run the synthetic API and frontend

Read [etl/docs/demo-runtime.md](../etl/docs/demo-runtime.md), then start an isolated
project from the repository root:

```sh
make demo-up
```

The default project is `factored-submission`, the API listens on
`http://127.0.0.1:18040`, and the runtime uses only team-generated synthetic fixtures.
Generated account credentials stay in private ignored files under
`etl/.demo/factored-submission/secrets/`. The runtime guide describes the synthetic
customer/agent identities and private account-file handling. Do not publish them.
No AWS credentials or organizer data downloads are needed.

In a second terminal, from the same root:

```sh
make frontend-dev
```

Open `http://127.0.0.1:5174/`. Vite proxies `/api` to the synthetic API on port 18040.
Use the generated local demo accounts according to the runtime guide. The frontend
needs a ready backend and provisioned synthetic accounts for login.

Stop Vite with Ctrl+C and stop only this runtime with:

```sh
make demo-down
```

Override `DEMO_PROJECT`, `DEMO_PORT`, and `FRONTEND_PORT` on each corresponding
command if the defaults are occupied. Keep project and API-port settings consistent
for start, frontend, and shutdown. The default adapter is an explicitly labeled
engineering stub. To select the local classifier:

```sh
DEMO_CONVERSATION_ADAPTER=classifier make demo-up
```

Verify the effective adapter using the runtime guide; neither mode connects to a real
bank or payment system. The current included backend is remote `main`, not the
unpublished candidate used for the reported 60-case regression. Its integration
capability and validation limits are recorded in [evidence.md](evidence.md).

## Snapshot layout notes

The component sources are preserved byte for byte. Upstream documentation can still
refer to the old independent repository directory names; root commands above use the
consolidated `etl/`, `backend/`, and `frontend/` paths. Organizer PDF references are
retained as historical citations, but the PDFs are deliberately absent.

The optional backend exploration notebook refers to an ignored ETL ML fixture pack
at its original separate-checkout path. That pack is not bundled and is not required
for the API, frontend, classifier inference, or component checks.

The ETL system evaluator checks independent Git checkout identity against original
component commits. A consolidated snapshot has the hub's Git identity, so use original
standalone component checkouts for that evaluator rather than substituting the hub
commit. The exact reported regression additionally requires a backend candidate that
has not been published. `make check` and the synthetic runtime do not claim to reproduce
that regression.
