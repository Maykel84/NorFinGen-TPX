# Archived one-off migrations

These scripts were run once to fix specific historical data issues.
They are kept for reference but are not part of the regular workflow.
Do not re-run without understanding why each one existed — see
docs/PROJECT_HISTORY.md and docs/SESSION_HANDOFF.md for context.

- `fix_missing_payroll_transactions.py` — added missing bank transactions
  for 91 historical salary payments (2026-08)
- `fix_future_dated_records.py` — cleaned records created by a backfill
  bug that generated data beyond today's date
- `fix_stale_supplier_names_in_vouchers.py` — corrected voucher
  descriptions after a supplier name update in `roster.py`
- `update_paid_status.py` — one-time invoice status migration (Etap 3)
