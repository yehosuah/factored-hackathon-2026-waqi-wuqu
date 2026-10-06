# Dataset profiler

From this repository's root, synchronize the locked environment after installing this
version: `uv sync --locked`.

```bash
# Resolve the authoritative publication through PostgreSQL, then read local Parquet.
uv run --locked factored-profile --release current

# Portable inspection of a specific CURATED release, without PostgreSQL or AWS.
uv run --locked factored-profile --release <curated_release_id>

# A portable release lives below <data-root>/releases/<curated_release_id>/.
uv run --locked factored-profile --release <curated_release_id> --data-root /private/curated
```

`--data-root` defaults to `ETL_OUTPUT_ROOT`, or `data/processed`. PostgreSQL lookup uses
the existing `ETL_DB_*` environment configuration, including `ETL_DB_PASSWORD_FILE`.
It never initializes schemas or writes database state. The host must be able to reach
the configured database; Compose's internal hostname is not automatically reachable
from a host terminal. An explicit ID makes no database connection and reports
`publication_status: not_checked`. It never uses the raw release as a replacement.

Output: `outputs/profiles/<curated_release_id>/profile.json`; change the parent with
`--output-root`. Outputs are already ignored by Git. The JSON is private (mode 0600),
written atomically after complete validation. Existing profiles survive failed runs.
The destination cannot be inside the configured curated or raw source directories.

The terminal prints a concise aggregate summary. The JSON contract and definitions
are in [the feature design](design/dataset-profiler.md). Rejection counts come from
the manifest; nulls, distributions, repetition and temporal checks use accepted Parquet.
Overlapping rejection reasons do not add up to unique rejected rows. Unknown categorical
values are suppressed without changing their counts. Extend the display vocabulary
only after reviewing new values privately and updating tests.

| Exit | Meaning |
| --- | --- |
| 0 | Complete profile, possibly with observed quality/modeling notices |
| 1 | Unexpected failure or interruption; no successful new report |
| 2 | Invalid CLI arguments or release ID |
| 3 | Curated release or published pointer unavailable |
| 4 | Malformed, incompatible, changed or unreconciled input |
| 5 | PostgreSQL publication lookup/configuration unavailable |
| 6 | Output location unsafe or output write failed |

Failures emit a small JSON error on stderr, with fixed codes and no exception payloads.
Semantic observations are not automatically business errors or acceptance gates.
No charts, models, source downloads or ETL transformations are run by this command.
