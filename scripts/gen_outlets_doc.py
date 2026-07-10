"""Keep docs/outlets.md automatically in sync with config/outlets.yaml.

The outlet table in the docs is generated, never hand-edited: this script
renders it from the config, and tests/test_docs.py fails CI whenever the
committed file differs from what the config would generate. To update docs
after changing outlets: uv run python scripts/gen_outlets_doc.py
"""

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "outlets.yaml"
TARGET = ROOT / "docs" / "outlets.md"

HEADER = """\
# Outlets collected

<!-- GENERATED FILE — do not edit by hand.
     Source: config/outlets.yaml
     Regenerate: uv run python scripts/gen_outlets_doc.py -->

The outlets tiltmeter currently collects from, straight from
[`config/outlets.yaml`](../config/outlets.yaml). Selection criteria and the
swap policy for dead feeds are documented in
[METHODOLOGY.md, decision D4](../METHODOLOGY.md#d4-twenty-outlets-deliberately-spread-chosen-once-and-openly);
individual swaps are recorded in the [CHANGELOG](../CHANGELOG.md).

Ownership is sourced factual context (see the `ownership` blocks in the
config for source URLs, retrieval dates, and verification status); it is
never a scoring input.

| Outlet | Owner | Type | Feed |
|---|---|---|---|
"""


def render() -> str:
    with open(CONFIG) as f:
        outlets = yaml.safe_load(f)["outlets"]
    rows = [
        f"| [{o['name']}]({o['homepage']}) | {o['ownership']['owner']} "
        f"| {o['ownership']['type']} | <{o['feed']}> |"
        for o in sorted(outlets, key=lambda o: o["name"])
    ]
    return HEADER + "\n".join(rows) + f"\n\nTotal: {len(outlets)} outlets.\n"


if __name__ == "__main__":
    content = render()
    if "--check" in sys.argv:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != content:
            print("docs/outlets.md is stale; run: uv run python scripts/gen_outlets_doc.py")
            sys.exit(1)
        print("docs/outlets.md is in sync")
    else:
        TARGET.write_text(content, encoding="utf-8")
        print(f"wrote {TARGET}")
