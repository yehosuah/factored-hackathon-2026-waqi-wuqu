"""Create private bind-mount roots as their non-root host owner; never chown data."""

import json
import os
from pathlib import Path


def initialize(root):
    if os.geteuid() == 0:
        raise ValueError("run_as_non_root_state_owner")
    root = Path(root).resolve()
    for name in ("data/raw", "outputs/extract", "data/processed"):
        directory = Path(root) / name
        if directory.is_symlink() or not directory.resolve().is_relative_to(root):
            raise ValueError("unsafe_state_directory")
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if directory.stat().st_uid != os.geteuid() or not os.access(
            directory, os.R_OK | os.W_OK | os.X_OK
        ):
            raise ValueError("state_directory_requires_owner_access")
    return {"status": "ready", "ETL_UID": os.geteuid(), "ETL_GID": os.getegid()}


if __name__ == "__main__":
    print(json.dumps(initialize(Path(__file__).resolve().parents[1])))
