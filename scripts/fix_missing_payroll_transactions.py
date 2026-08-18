"""
Jednorazowa migracja: tworzy brakujące OUTGOING BankTransaction (+ Voucher BANK)
dla salary_transactions, które nigdy nie dostały odpowiadającej wypłaty
bankowej — bank_transaction_generator.py nigdy nie miał logiki dla payrollu
w ogóle (luka od Tier 2, nie regresja Fazy 6, zob. docs/SESSION_HANDOFF.md).

W przeciwieństwie do fix_outgoing_transactions.py (który ma wszystkie
potrzebne kwoty wprost w supplier_invoices) — kwoty netto/skattetrekk/AGA
per miesiąc NIE są zdenormalizowane nigdzie w jednej tabeli w wygodnej
formie. Zamiast składać je ręcznie z JOIN-a salary_specifications, ten
skrypt PONOWNIE WOŁA salary_generator.generate_monthly_salary(year, month)
— w pełni deterministyczne (brak losowości w payrollu), więc dla każdego
historycznego (year, month) odtwarza DOKŁADNIE te same Vouchery/kwoty, co
już są zapisane w bazie. `transaction.id` z tej świeżej regeneracji jest
None (nowy obiekt) — podmieniany na prawdziwe ID z bazy (znalezione po
naturalnym kluczu year+month) przed zbudowaniem płatności, żeby
salary_transaction_id FK wskazywał na właściwy wiersz.

Uruchomienie:
    python scripts/fix_missing_payroll_transactions.py

Weryfikacja:
    SELECT COUNT(*) FROM salary_transactions st
    WHERE NOT EXISTS (SELECT 1 FROM bank_transactions bt WHERE bt.salary_transaction_id = st.id);
    Oczekiwane: 0.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from norfingen.db.repository import get_connection, save_bank_transactions  # noqa: E402
from norfingen.generators.bank_transaction_generator import generate_payroll_bank_transaction  # noqa: E402
from norfingen.generators.salary_generator import generate_monthly_salary  # noqa: E402

FIND_MISSING_SQL = """
    SELECT st.id, st.year, st.month
    FROM salary_transactions st
    WHERE NOT EXISTS (
        SELECT 1 FROM bank_transactions bt WHERE bt.salary_transaction_id = st.id
    )
    ORDER BY st.year, st.month
"""


def main() -> None:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(FIND_MISSING_SQL)
        rows = cur.fetchall()

    print(f"Znaleziono {len(rows)} list płac bez transakcji bankowej OUTGOING")

    pairs = []
    skipped_zero = 0
    for transaction_id, year, month in rows:
        transaction, vouchers = generate_monthly_salary(year, month)
        transaction.id = transaction_id  # prawdziwe ID z bazy, nie świeżo wygenerowane None
        result = generate_payroll_bank_transaction(transaction, vouchers)
        if result is None:
            skipped_zero += 1  # nie powinno się zdarzyć dla prawdziwej listy płac, ale zabezpieczone
            continue
        pairs.append(result)

    if pairs:
        save_bank_transactions(pairs)

    print(f"Zapisano {len(pairs)} transakcji payrollowych (pominięto {skipped_zero} zerowych)")

    with conn.cursor() as cur:
        cur.execute("SELECT transaction_type, COUNT(*), ROUND(SUM(amount)) FROM bank_transactions GROUP BY 1 ORDER BY 1")
        print("Stan po migracji:", cur.fetchall())
        cur.execute("""
            SELECT COUNT(*) FROM salary_transactions st
            WHERE NOT EXISTS (SELECT 1 FROM bank_transactions bt WHERE bt.salary_transaction_id = st.id)
        """)
        print("Nadal brakujące (oczekiwane 0):", cur.fetchone())


if __name__ == "__main__":
    main()
