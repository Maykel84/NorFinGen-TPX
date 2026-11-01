#!/bin/bash
# Full regeneration of the history into a LOCAL scratch Postgres (never production).
#
#   DATABASE_URL=postgresql://user@127.0.0.1:54329/scratch scripts/local_regen.sh [last-day]
#
# 1. create/refresh the schema, TRUNCATE the transactional tables (RESTART IDENTITY: ids start from 1 again)
# 2. one pipeline, every calendar day from 2019-01-01 to last-day (default: today)
#
# It refuses to run unless the database host is local: it TRUNCATEs. The same pipeline
# is what the cron runs for the current day, so this is also the reference for
# "history and a normal day behave identically" (tests/db_fingerprint.py).
set -euo pipefail

: "${DATABASE_URL:?set DATABASE_URL to the local scratch database}"
case "$DATABASE_URL" in
  *@127.0.0.1:*|*@localhost:*|*@\[::1\]:*) ;;
  *) echo "refusing to run: DATABASE_URL is not a local database" >&2; exit 1;;
esac

cd "$(dirname "$0")/.."
PY="${PYTHON:-python}"
LAST_DAY="${1:-}"

echo "[$(date +%T)] schema + reference data, then TRUNCATE the transactional tables (local)"
PYTHONPATH=src "$PY" - <<'EOF'
import os, psycopg2
from norfingen.db.repository import ensure_schema, seed_reference_data
ensure_schema(); seed_reference_data()
conn = psycopg2.connect(os.environ["DATABASE_URL"]); conn.autocommit = True
cur = conn.cursor()
cur.execute("""TRUNCATE orders, order_lines, supplier_invoices, salary_transactions, payslips, salary_specifications,
               vouchers, postings, bank_transactions, hour_entries, generation_state RESTART IDENTITY CASCADE""")
EOF

echo "[$(date +%T)] pipeline: 2019-01-01 -> ${LAST_DAY:-today}"
if [ -n "$LAST_DAY" ]; then
  "$PY" run_backfill.py --start 2019-01-01 --end "$LAST_DAY"
else
  "$PY" run_backfill.py --start 2019-01-01
fi
echo "[$(date +%T)] done"
