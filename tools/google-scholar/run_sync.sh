#!/usr/bin/env bash

set -euo pipefail

unset JANEWAY_SETTINGS_MODULE
unset DJANGO_SETTINGS_MODULE

BASE="/var/lib/janeway/gold-scholar"

exec 9>"$BASE/sync.lock"

if ! flock -n 9; then
    echo "Another Scholar synchronization is running."
    exit 0
fi

cd /var/www/janeway/src

echo "===== EXPORT PUBLISHED ARTICLES ====="

GOLD_SCHOLAR_JOURNAL=ua \
/var/www/janeway/venv/bin/python manage.py shell \
    < /opt/janeway-scholar/export_articles.py

echo "===== SCHOLAR CACHE SYNCHRONIZATION ====="

timeout --kill-after=15s 300s \
    /opt/janeway-scholar-venv/bin/python \
    /opt/janeway-scholar/cache_sync.py "$@"

echo "===== SYNCHRONIZATION COMPLETED ====="
