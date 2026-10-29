#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/src/plugins/submission_proof"

REPO="git@github.com:Nadia1gh/janeway-author-submission-proof.git"
COMMIT="8092a0c4ab274a15b0f7c7a4e84338ab6f437496"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

git clone --quiet "$REPO" "$TMP/repo"
git -C "$TMP/repo" checkout --quiet --detach "$COMMIT"

SOURCE="$TMP/repo/src/plugins/submission_proof"

test -f "$SOURCE/plugin_settings.py"

mkdir -p "$DEST"

cp -a "$SOURCE/." "$DEST/"
cp "$TMP/repo/requirements.add.txt" "$DEST/"
cp "$TMP/repo/README.md" "$DEST/"

echo "Submission Proof installed from commit $COMMIT"
