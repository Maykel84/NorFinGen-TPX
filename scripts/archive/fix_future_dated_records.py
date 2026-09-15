"""
Jednorazowa migracja (Faza 5a): usuwa wszystkie rekordy z datą późniejszą niż
dziś, powstałe przez błąd w generators/backfill.py — generate_and_persist_month()
przetwarzał CAŁY bieżący miesiąc kalendarzowy (na podstawie samego (rok,
miesiąc) z months_range()) bez sprawdzenia, czy poszczególne dni tego
miesiąca faktycznie już minęły. Błąd naprawiony w kodzie (zob.
seed.payroll.is_date_generatable/should_generate_monthly_salary,
generators.backfill.generate_and_persist_month/run_backfill) — ten skrypt
tylko czyści dane, które już powstały ZANIM naprawa weszła w życie.

NIE robi pełnego TRUNCATE — usuwa tylko rekordy z datą > dziś, w kolejności
respektującej FK (dzieci przed rodzicami; część relacji ma ON DELETE CASCADE
w schema.sql — order_lines/orders, payslips/salary_transactions,
salary_specifications/payslips, postings/vouchers — ale bank_transactions
odwołuje się do orders/supplier_invoices/vouchers BEZ cascade, więc te
kolumny (order_id/supplier_invoice_id/voucher_id) muszą być wyczyszczone
PRZED usunięciem rodziców, gdyby cokolwiek jednak istniało; w praktyce przy
tej naprawie 0 bank_transactions odwoływało się do przyszłych dat).

Uruchomienie:
    python scripts/fix_future_dated_records.py

Po migracji uruchom jeden dzień run_daily.py (naprawiony generator uzupełni
dzisiejsze dane poprawnie), potem scripts/fix_outgoing_transactions.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from datetime import date  # noqa: E402

from norfingen.db.repository import get_connection  # noqa: E402


def fix_future_dated_records() -> None:
    conn = get_connection()
    today = date.today()

    with conn.cursor() as cur:
        # Diagnostyka PRZED usunięciem — zapisana do logu naprawy.
        cur.execute("SELECT COUNT(*) FROM orders WHERE order_date > %s", (today,))
        n_orders = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM supplier_invoices WHERE invoice_date > %s", (today,))
        n_invoices = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM salary_transactions WHERE date > %s", (today,))
        n_salary = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM vouchers WHERE date > %s", (today,))
        n_vouchers = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM bank_transactions WHERE date > %s", (today,))
        n_bank = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM hour_entries WHERE date > %s", (today,))
        n_hours = cur.fetchone()[0]

        print(f"Przed migracją (rekordy z datą > {today}):")
        print(f"  orders={n_orders} supplier_invoices={n_invoices} salary_transactions={n_salary} "
              f"vouchers={n_vouchers} bank_transactions={n_bank} hour_entries={n_hours}")

        # Bank_transactions odwołuje się do orders/supplier_invoices/vouchers
        # BEZ ON DELETE CASCADE — musi zniknąć PRZED usunięciem rodziców,
        # gdyby cokolwiek jednak wskazywało na przyszłe daty (u nas: 0, ale
        # sprawdzone jawnie, nie założone).
        cur.execute(
            """DELETE FROM bank_transactions
               WHERE date > %(today)s
                  OR order_id IN (SELECT id FROM orders WHERE order_date > %(today)s)
                  OR supplier_invoice_id IN (SELECT id FROM supplier_invoices WHERE invoice_date > %(today)s)
                  OR voucher_id IN (SELECT id FROM vouchers WHERE date > %(today)s)""",
            {"today": today},
        )

        cur.execute("DELETE FROM hour_entries WHERE date > %s", (today,))

        # order_lines/payslips/salary_specifications/postings mają ON DELETE
        # CASCADE od odpowiednich rodziców (zob. schema.sql) — usuwane
        # automatycznie przez poniższe DELETE na orders/salary_transactions/
        # vouchers. Jawne DELETE tutaj i tak (defensywnie, brak efektu
        # ubocznego jeśli cascade już to zrobił).
        cur.execute("DELETE FROM order_lines WHERE order_id IN (SELECT id FROM orders WHERE order_date > %s)", (today,))
        cur.execute(
            "DELETE FROM salary_specifications WHERE payslip_id IN "
            "(SELECT id FROM payslips WHERE transaction_id IN "
            "(SELECT id FROM salary_transactions WHERE date > %s))",
            (today,),
        )
        cur.execute(
            "DELETE FROM payslips WHERE transaction_id IN (SELECT id FROM salary_transactions WHERE date > %s)",
            (today,),
        )
        cur.execute("DELETE FROM postings WHERE voucher_id IN (SELECT id FROM vouchers WHERE date > %s)", (today,))

        cur.execute("DELETE FROM vouchers WHERE date > %s", (today,))
        cur.execute("DELETE FROM salary_transactions WHERE date > %s", (today,))
        cur.execute("DELETE FROM orders WHERE order_date > %s", (today,))
        cur.execute("DELETE FROM supplier_invoices WHERE invoice_date > %s", (today,))

    conn.commit()

    with conn.cursor() as cur:
        checks = [
            ("orders", "order_date"), ("supplier_invoices", "invoice_date"),
            ("bank_transactions", "date"), ("hour_entries", "date"),
            ("salary_transactions", "date"), ("vouchers", "date"),
        ]
        print(f"\nPo migracji (rekordy z datą > {today}, wszystkie powinny być 0):")
        all_zero = True
        for table, col in checks:
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} > %s", (today,))
            count = cur.fetchone()[0]
            all_zero = all_zero and count == 0
            print(f"  {table}: {count}")
        print("\nOK — brak rekordów w przyszłości." if all_zero else "\nUWAGA — nadal są rekordy w przyszłości!")


if __name__ == "__main__":
    fix_future_dated_records()
