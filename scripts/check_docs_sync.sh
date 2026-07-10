#!/usr/bin/env bash
# Docs move with the code, enforced: if pipeline code or config changed in a
# commit range but no documentation did, fail. Used by CI (ci.yml) and usable
# locally: scripts/check_docs_sync.sh <base>..<head>
set -euo pipefail

range="${1:?usage: check_docs_sync.sh <base>..<head>}"

changed="$(git diff --name-only "$range")"

code_changed="$(echo "$changed" | grep -E '^(src/|config/)' || true)"
docs_changed="$(echo "$changed" | grep -E '^(docs/|METHODOLOGY\.md|CHANGELOG\.md|README\.md)' || true)"

if [[ -n "$code_changed" && -z "$docs_changed" ]]; then
    echo "FAIL: code/config changed without any docs change in $range"
    echo
    echo "Changed code/config files:"
    echo "$code_changed" | sed 's/^/  /'
    echo
    echo "Update the relevant docs (METHODOLOGY.md decision block, CHANGELOG.md"
    echo "entry, docs/*) in the same change. Docs are part of the product here."
    exit 1
fi

echo "docs-sync ok"
