import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "pages" / "schedule" / "generated"


def sha256_digest(content):
    return hashlib.sha256(content).hexdigest()


def write_if_changed(path, content, label):
    previous = path.read_bytes() if path.exists() else None
    if previous == content:
        print(
            f"Asset unchanged: path={path.relative_to(ROOT)} "
            f"sha256={sha256_digest(content)[:12]} bytes={len(content)} label={label}"
        )
        return False

    path.write_bytes(content)
    action = "created" if previous is None else "updated"
    detail = (
        f"old_sha256={sha256_digest(previous)[:12]} old_bytes={len(previous)} "
        if previous is not None
        else ""
    )
    print(
        f"Asset {action}: path={path.relative_to(ROOT)} "
        f"{detail}new_sha256={sha256_digest(content)[:12]} new_bytes={len(content)} label={label}"
    )
    return True


def remove_stale_outputs(glob_pattern, expected_paths):
    expected_names = {path.name for path in expected_paths}
    removed = []
    for path in OUTPUT_DIR.glob(glob_pattern):
        if path.name in expected_names:
            continue
        path.unlink()
        removed.append(path.name)
    if removed:
        print(
            f"Removed stale outputs: pattern={glob_pattern} count={len(removed)} files={', '.join(sorted(removed))}"
        )
    else:
        print(f"Removed stale outputs: pattern={glob_pattern} count=0")


def load_week_payload(path):
    return json.loads(path.read_text(encoding="utf-8"))
