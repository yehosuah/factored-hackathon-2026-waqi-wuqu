# Source and local setup

These commands check the public ETL and backend components independently. Requirements:
Git, `uv`, Python 3.13 (managed by the locked environments), and Docker Compose for the
optional synthetic runtime. Run each component's checks in its own directory.

```sh
git clone https://github.com/yehosuah/FactoredAI_base.git
git clone https://github.com/yehosuah/FactoredAI_BCK.git
```

From `FactoredAI_base`:

```sh
uv sync --locked --no-editable --reinstall-package factored-bank
UV_NO_EDITABLE=1 make check
UV_NO_EDITABLE=1 make test
```

From `FactoredAI_BCK`:

```sh
uv sync --locked
make check
```

Backend PostgreSQL regressions need `initdb` and `pg_ctl`; its README documents that
missing executables cause those tests to be skipped. A passing partial suite does not
replace the database tests.

## Synthetic runtime

Read the ETL's [portable runtime guide](https://github.com/yehosuah/FactoredAI_base/blob/main/docs/demo-runtime.md)
before starting. From `FactoredAI_base`, with the backend clone as a sibling directory:

```sh
python3 scripts/demo.py up --backend-path ../FactoredAI_BCK
```

The documented default is an explicitly labeled engineering stub with synthetic
fixtures. The API binds to loopback. The guide describes private local account files,
cleanup, the optional classifier mode, and how to verify the effective adapter.
Use only generated synthetic credentials and data; no organizer download or AWS
credentials are needed. The current public backend revision has not been validated
against the integrated regression reported in this hub.

The frontend source remains private pending organizer-material clearance; this hub
therefore does not provide a publicly cloneable end-to-end UI setup yet.
