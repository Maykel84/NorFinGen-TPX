"""
Jednorazowa migracja: tworzy brakujące OUTGOING BankTransaction (+ Voucher BANK)
dla supplier_invoices, które mają status='PAID' i payment_due_date w przeszłości,
ale nigdy nie dostały odpowiadającej transakcji bankowej — luka po starej
heurystyce statusu w supplier_invoice_generator.py (ustawiała PAID na podstawie
upływu czasu, sprzed wdrożenia realnego BankTransaction/Voucher(BANK)).

NOTE: obsolete after phase 0.5b (invoice status then follows the payments, so this gap cannot
appear and the script is deleted). Until then it still reproduces history after a TRUNCATE.

Uruchomienie:
    python scripts/fix_outgoing_transactions.py

Weryfikacja:
    SELECT transaction_type, COUNT(*) FROM bank_transactions GROUP BY 1;
    Oczekiwane: INCOMING ~717, OUTGOING ~545 (tyle ile jest PAID faktur zakupu).
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from norfingen.db.repository import get_connection, save_bank_transactions  # noqa: E402
from norfingen.generators.voucher import Posting, Voucher, VoucherType, acct, assert_voucher_valid  # noqa: E402
from norfingen.models.bank_transaction import BankTransaction, BankTransactionType  # noqa: E402
from norfingen.models.base import TripletexRef  # noqa: E402
from norfingen.seed.workdays import next_working_day  # noqa: E402

ACCOUNT_BANK = 1910  # Bankinnskudd, driftskonto
ACCOUNT_LEVERANDORGJELD = 2400  # Leverandørgjeld

FIND_MISSING_SQL = """
    SELECT si.id, si.invoice_number, si.supplier_id, si.payment_due_date,
           si.amount_currency, s.name
    FROM supplier_invoices si
    JOIN suppliers s ON s.id = si.supplier_id
    WHERE si.status = 'PAID'
      AND si.payment_due_date < CURRENT_DATE
      AND NOT EXISTS (
          SELECT 1 FROM bank_transactions bt
          WHERE bt.supplier_invoice_id = si.id AND bt.transaction_type = 'OUTGOING'
      )
"""


def build_outgoing_fix(invoice_id: int, invoice_number: str, supplier_id: int,
                        payment_due_date, amount_currency, supplier_name: str) -> tuple[BankTransaction, Voucher]:
    amount = round(float(amount_currency), 2)
    supplier_ref = TripletexRef(id=supplier_id)
    # Phase 0.5a: the bank books on working days only - a due date on Sat/Sun is paid on Monday,
    # the same rule bank_transaction_generator.build_outgoing_payment applies.
    payment_due_date = next_working_day(payment_due_date)

    transaction = BankTransaction(
        date=payment_due_date,
        amount=amount,
        transaction_type=BankTransactionType.OUTGOING,
        description=f"Betaling til {supplier_name}",
        supplier_id=supplier_id,
        supplier_invoice_id=invoice_id,
        account_from=ACCOUNT_LEVERANDORGJELD,
        account_to=ACCOUNT_BANK,
    )

    voucher = Voucher(
        date=payment_due_date,
        description=f"Betaling til {supplier_name} — {invoice_number}",
        voucherType=VoucherType.BANK,
        postings=[
            Posting(date=payment_due_date, account=acct(ACCOUNT_LEVERANDORGJELD), amount=amount, supplier=supplier_ref),
            Posting(date=payment_due_date, account=acct(ACCOUNT_BANK), amount=-amount, supplier=supplier_ref),
        ],
    )
    assert_voucher_valid(voucher)
    return transaction, voucher


def main() -> None:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(FIND_MISSING_SQL)
        rows = cur.fetchall()

    print(f"Znaleziono {len(rows)} faktur PAID bez transakcji OUTGOING")

    # A weekend due date moves to Monday; never create a payment dated in the future.
    rows = [row for row in rows if next_working_day(row[3]) <= date.today()]
    pairs = [build_outgoing_fix(*row) for row in rows]
    if pairs:
        save_bank_transactions(pairs)

    with conn.cursor() as cur:
        cur.execute("SELECT transaction_type, COUNT(*) FROM bank_transactions GROUP BY 1 ORDER BY 1")
        print("Stan po migracji:", cur.fetchall())


if __name__ == "__main__":
    main()
