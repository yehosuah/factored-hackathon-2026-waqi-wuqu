"""Verify the checked-in component snapshots against their source manifest."""

import hashlib
import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "source-manifest.json").read_text())
    if manifest["backend_local_candidate_included"]:
        raise SystemExit("Unpublished backend candidate must not be included")
    total = 0
    for name, component in manifest["components"].items():
        directory = root / name
        if (directory / ".git").exists():
            raise SystemExit(f"Nested Git checkout: {name}")
        for item in component["files"]:
            path = directory / item["path"]
            if path.is_symlink() or not path.is_file():
                raise SystemExit(f"Missing or unsafe source: {name}/{item['path']}")
            data = path.read_bytes()
            if (
                len(data) != item["bytes"]
                or hashlib.sha256(data).hexdigest() != item["sha256"]
            ):
                raise SystemExit(f"Source differs from snapshot: {name}/{item['path']}")
            blob = hashlib.sha1(
                b"blob " + str(len(data)).encode() + b"\0" + data
            ).hexdigest()
            if blob != item["git_blob"]:
                raise SystemExit(f"Git blob mismatch: {name}/{item['path']}")
            if bool(path.stat().st_mode & 0o111) != (item["mode"] == "100755"):
                raise SystemExit(f"Source mode differs: {name}/{item['path']}")
        for excluded in component["excluded_files"]:
            if (directory / excluded["path"]).exists():
                raise SystemExit(
                    f"Excluded artifact present: {name}/{excluded['path']}"
                )
        total += len(component["files"])
        print(
            f"{name}: {len(component['files'])} files match {component['source_commit']}"
        )
    print(f"Verified {total} source files; original snapshots are unchanged.")


if __name__ == "__main__":
    main()
