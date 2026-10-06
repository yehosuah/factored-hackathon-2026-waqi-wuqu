FROM ghcr.io/astral-sh/uv:0.12.0@sha256:606e70c71c852d03f611b1e56a195d08648507018a7057fab82c4974c4eae105 AS uv
FROM python:3.13.16-slim-trixie@sha256:3dd7cc108ec1493442514f5c2a871af6af0ec31d768ff6e378a93340c3b3db5f AS base
COPY docker/debian.sources /etc/apt/sources.list.d/debian.sources
RUN apt-get update \
    && apt-get upgrade --yes --no-install-recommends \
    && apt-get install --yes --no-install-recommends libpcre2-8-0=10.46-1~deb13u3 libpq5=17.11-0+deb13u1 \
    && rm -rf /var/lib/apt/lists/*

FROM base AS builder
RUN apt-get update \
    && apt-get install --yes --no-install-recommends gcc libc6-dev libpq-dev=17.11-0+deb13u1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
# Start with locked, hashed wheels for every build tool. Build source packages in
# that environment, then remove build tools; the runtime dependency closure contains none of them.
RUN uv sync --locked --only-group build-tools --no-build \
    && uv sync --locked --no-dev --group native --group build-tools --no-editable --no-build-isolation \
    && uv pip uninstall --python /app/.venv/bin/python cython hatchling packaging pathspec pluggy setuptools tomlkit trove-classifiers wheel

FROM base AS runtime
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PSYCOPG_IMPL=c
ENV FACTORED_PROVENANCE_ROOT=/app
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY pyproject.toml uv.lock /app/
USER 65532:65532
HEALTHCHECK --interval=30s --timeout=5s --start-period=600s --retries=3 \
    CMD ["python", "-m", "factored_bank.etl.health"]
CMD ["factored-etl", "serve"]
