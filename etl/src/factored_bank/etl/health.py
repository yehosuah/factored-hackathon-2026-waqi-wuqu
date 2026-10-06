"""Container health tracks scheduler progress independently of the last accepted data."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path


def main():
    try:
        status = json.loads(
            (Path(os.getenv("ETL_OUTPUT_ROOT", "/state/processed")) / "status.json").read_text()
        )
        reference = status.get("finished_at") or status["started_at"]
        age = (datetime.now(UTC) - datetime.fromisoformat(reference)).total_seconds()
        limit = int(os.getenv("ETL_HEALTH_MAX_AGE_SECONDS", "1800"))
        return 0 if status["status"] in ("running", "succeeded") and age <= limit else 1
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
