"""Create private runtime secrets without printing or replacing existing values."""

import os
import secrets
from pathlib import Path

os.umask(0o077)
root = Path(__file__).resolve().parents[1] / ".secrets"
root.mkdir(mode=0o700, exist_ok=True)
for name in ("postgres_password", "etl_password", "backend_password", "demo_password"):
    path = root / name
    if not path.exists():
        with path.open("x") as f:
            f.write(secrets.token_urlsafe(32) + "\n")
        os.chmod(path, 0o600)
for name in ("aws_credentials", "aws_config"):
    path = root / name
    if not path.exists():
        path.touch(mode=0o600)
print("Runtime secrets available in .secrets/; values are not printed.")
