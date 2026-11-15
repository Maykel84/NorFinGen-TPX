#!/bin/bash
# Full regeneration of the history in the PRODUCTION database (Supabase) - the deployment of accounting phases 0.5-6.
#
#   PROD_REGEN_CONFIRM=I-HAVE-A-BACKUP scripts/prod_regen.sh <backup.dump> [last-day]
#
# What it does, in this order, stopping at the first error:
#   1. refuses to run without the confirmation variable, or without a non-empty backup file (pg_restore --list must work)
#   2. refuses to run against a LOCAL database (that is scripts/local_regen.sh's job - this one must never be mistaken for it)
#   3. prints row counts before, applies db/schema.sql + reference data (ensure_schema, seed_reference_data)
#   4. TRUNCATEs the transactional tables (RESTART IDENTITY CASCADE); reference tables, api_keys and roles are NOT touched
#   5. run_backfill.py: every calendar day from 2019-01-01 to last-day (default: today), resumable (watermark, idempotent writes)
#
# The cron (GitHub Actions daily.yml) must be DISABLED before this runs; the script cannot check it.
set -euo pipefail

BACKUP="${1:?usage: PROD_REGEN_CONFIRM=I-HAVE-A-BACKUP scripts/prod_regen.sh <backup.dump> [last-day]}"
LAST_DAY="${2:-}"
[ "${PROD_REGEN_CONFIRM:-}" = "I-HAVE-A-BACKUP" ] || { echo "refusing: set PROD_REGEN_CONFIRM=I-HAVE-A-BACKUP" >&2; exit 1; }
[ -s "$BACKUP" ] || { echo "refusing: backup file '$BACKUP' missing or empty" >&2; exit 1; }
PGBIN="${PG_BIN:-/Applications/Postgres.app/Contents/Versions/latest/bin}"
"$PGBIN/pg_restore" --list "$BACKUP" > /dev/null || { echo "refusing: '$BACKUP' is not a readable pg_dump archive" >&2; exit 1; }

cd "$(dirname "$0")/.."
PY="${PYTHON:-python}"

PYTHONPATH=src "$PY" - <<'PYEOF'
import os
from urllib.parse import urlparse
from dotenv import load_dotenv
load_dotenv(os.path.join(os.getcwd(), ".env"))  # explicit path: find_dotenv() fails when the code comes from stdin
url = os.environ.get("DATABASE_URL", "")
host = urlparse(url).hostname
if not host or host in ("127.0.0.1", "localhost", "::1"):
    raise SystemExit("refusing: DATABASE_URL is local or missing - this script is for the production database")
print(f"target host: {host}")
PYEOF

echo "[$(date +%T)] row counts BEFORE"
PYTHONPATH=src "$PY" - <<'PYEOF'
from norfingen.db.repository import get_connection
cur = get_connection().cursor()
for t in ("orders", "vouchers", "postings", "bank_transactions", "hour_entries", "supplier_invoices", "api_keys"):
    cur.execute(f"SELECT COUNT(*) FROM {t}")
    print(f"  {t:20} {cur.fetchone()[0]}")
PYEOF

echo "[$(date +%T)] schema + reference data, then TRUNCATE the transactional tables"
PYTHONPATH=src "$PY" - <<'PYEOF'
from norfingen.db.repository import ensure_schema, get_connection, seed_reference_data
ensure_schema(); seed_reference_data()
conn = get_connection()
cur = conn.cursor()
cur.execute("""TRUNCATE orders, order_lines, supplier_invoices, salary_transactions, payslips, salary_specifications,
               vouchers, postings, bank_transactions, hour_entries, generation_state RESTART IDENTITY CASCADE""")
conn.commit()
print("  truncated")
PYEOF

echo "[$(date +%T)] pipeline: 2019-01-01 -> ${LAST_DAY:-today}"
if [ -n "$LAST_DAY" ]; then
  "$PY" run_backfill.py --start 2019-01-01 --end "$LAST_DAY"
else
  "$PY" run_backfill.py --start 2019-01-01
fi
echo "[$(date +%T)] done"
