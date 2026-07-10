"""How does anything become a published file?

One writer, one reader, one naming rule for everything under releases/.
Artifacts must be byte-identical wherever they are produced, so the writer
pins everything a platform could vary: UTF-8 encoding (never the locale),
sorted keys (never dict order), no ASCII escaping, one trailing newline.

The KINDS table is the single home of the artifact naming convention; the
API's route table is generated from it, so a new artifact kind becomes
servable by adding one line here.
"""

import json
from pathlib import Path

# kind -> filename prefix; API route name == kind
KINDS = {
    "manifests": "manifest",
    "ratings": "ratings",
    "stories": "stories",
    "validation": "validation",
    "sweeps": "sweep",
}


def artifact_path(out_dir: str | Path, kind: str, snapshot_id: str) -> Path:
    return Path(out_dir) / f"{KINDS[kind]}-{snapshot_id}.json"


def write_json(path: str | Path, payload) -> Path:
    """Deterministic serialization: same payload, same bytes, any machine."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    return path


def write(out_dir: str | Path, kind: str, snapshot_id: str, payload) -> Path:
    return write_json(artifact_path(out_dir, kind, snapshot_id), payload)


def read_json(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
