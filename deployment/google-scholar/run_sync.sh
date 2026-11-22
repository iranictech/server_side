#!/usr/bin/env bash
set -euo pipefail

# Required configuration.
: "${JANEWAY_SRC:?JANEWAY_SRC is required}"
: "${JANEWAY_PYTHON:?JANEWAY_PYTHON is required}"
: "${SCHOLAR_PYTHON:?SCHOLAR_PYTHON is required}"
: "${GOLD_SCHOLAR_JOURNAL:?GOLD_SCHOLAR_JOURNAL is required}"
: "${GOLD_SCHOLAR_JOURNAL_ID:?GOLD_SCHOLAR_JOURNAL_ID is required}"
: "${GOLD_SCHOLAR_CACHE_DIR:?GOLD_SCHOLAR_CACHE_DIR is required}"

unset JANEWAY_SETTINGS_MODULE
unset DJANGO_SETTINGS_MODULE

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BASE="$GOLD_SCHOLAR_CACHE_DIR"

test -f "$JANEWAY_SRC/manage.py"
test -x "$JANEWAY_PYTHON"
test -x "$SCHOLAR_PYTHON"
test -f "$SCRIPT_DIR/src/export_articles.py"
test -f "$SCRIPT_DIR/src/cache_sync.py"
test -d "$BASE"

case "$GOLD_SCHOLAR_JOURNAL_ID" in
    *[!0-9]*|"")
        echo "Invalid journal ID" >&2
        exit 1
        ;;
esac

if [ "$GOLD_SCHOLAR_JOURNAL_ID" -eq 0 ]; then
    echo "Journal ID must be positive" >&2
    exit 1
fi

export GOLD_SCHOLAR_JOURNAL
export GOLD_SCHOLAR_JOURNAL_ID
export GOLD_SCHOLAR_CACHE_DIR

exec 9>"$BASE/sync.lock"

if ! flock -n 9; then
    echo "Another Scholar synchronization is running."
    exit 0
fi

cd "$JANEWAY_SRC"

echo "===== EXPORT PUBLISHED ARTICLES ====="

"$JANEWAY_PYTHON" manage.py shell \
    < "$SCRIPT_DIR/src/export_articles.py"

echo "===== SCHOLAR CACHE SYNCHRONIZATION ====="

timeout --kill-after=15s 300s \
    "$SCHOLAR_PYTHON" \
    "$SCRIPT_DIR/src/cache_sync.py" "$@"

echo "===== SYNCHRONIZATION COMPLETED ====="
